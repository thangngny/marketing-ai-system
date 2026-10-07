"""The tool catalog: small, explicit, typed tools grouped by namespace.

Handlers only translate between the canonical model and a connector. They never
decide policy; the hub already did.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..capabilities import KNOWN_BLOCKERS, connector_status
from ..config import Settings
from ..connectors import ConnectorRegistry
from ..constants import ConnectorState, Impact
from ..fixtures import mock_campaign_metrics, mock_crm_accounts, mock_logistics_leads
from ..models import EmailDraft, LeadCandidate, MetricSnapshot, TaskProposal
from ..policy import PolicyEngine
from ..workflows.approvals import ApprovalEngine, BuzzSignedEventVerifier
from ..workflows.store import WorkflowStore
from .hub import HubRuntime, ToolHub, ToolSpec, ToolUnavailable


# --------------------------------------------------------------------------- inputs
class NoInput(BaseModel):
    pass


class StatusIn(BaseModel):
    live_probe: bool = Field(False, description="Run non-destructive live probes (may use provider quota).")


class LimitIn(BaseModel):
    limit: int = Field(10, ge=1, le=200)


class FindExistingIn(BaseModel):
    companies: list[str] = Field(default_factory=list, max_length=100)
    domains: list[str] = Field(default_factory=list, max_length=100)


class TaskIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    related_company: str = Field(min_length=1, max_length=200)
    due_in_days: int = Field(3, ge=0, le=90)
    reason: str = Field("", max_length=1000)
    owner_hint: str | None = None


class DeleteRecordIn(BaseModel):
    module: Literal["Leads", "Contacts", "Accounts", "Deals", "Tasks"]
    record_id: str


class SearchCompaniesIn(BaseModel):
    industry: str = "logistics"
    keywords: list[str] = Field(default_factory=list)
    location: str = "Vietnam"
    limit: int = Field(10, ge=1, le=25)


class SearchPeopleIn(BaseModel):
    domains: list[str] = Field(default_factory=list, max_length=25)
    titles: list[str] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=25)


class EmailDraftIn(BaseModel):
    lead_company: str
    to_name: str | None = None
    to_email: str | None = None
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=8000)


class SendEmailIn(BaseModel):
    to_email: str
    subject: str
    body: str


class SearchDocsIn(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(10, ge=1, le=50)


class ReadDocIn(BaseModel):
    file_id: str = Field(..., description="ID của tệp tin trên Google Drive")
    max_chars: int = Field(50000, ge=500, le=200000, description="Số lượng ký tự tối đa cần đọc")


class PublishPostIn(BaseModel):
    channel: Literal["linkedin", "facebook", "youtube", "tiktok", "zalo"]
    text: str = Field(min_length=10, max_length=3000)


class PagePostDraftIn(BaseModel):
    message: str = Field(min_length=10, max_length=3000)


class TikTokDraftIn(BaseModel):
    title: str = Field(min_length=3, max_length=200, description="Tiêu đề hoặc caption video TikTok.")
    video_source: str = Field(description="URL hoặc đường dẫn file video để tải nháp.")
    privacy_level: str = Field("SELF_ONLY", description="Mức độ riêng tư: SELF_ONLY (chỉ mình tôi - Sandbox).")


class AdsPerfIn(BaseModel):
    platform: Literal["meta", "google"]
    days: int = Field(30, ge=1, le=90)


class LaunchCampaignIn(BaseModel):
    platform: Literal["meta", "google"]
    name: str
    daily_budget_vnd: int = Field(ge=0)


class ChangeBudgetIn(BaseModel):
    platform: Literal["meta", "google"]
    campaign_id: str
    new_daily_budget_vnd: int = Field(ge=0)


class ContentDraftIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    channel: str
    body: str = Field(min_length=20, max_length=20000)


class CodexRunIn(BaseModel):
    prompt: str = Field(..., description="Prompt or task instructions to execute via OpenAI Codex CLI/App")
    cwd: str = Field("C:/Users/Admin", description="Working directory for task execution")
    model: str | None = Field(None, description="Optional model override (defaults to config: gpt-5.6-sol)")


class CodexOpenIn(BaseModel):
    pass


class CodexStatusIn(BaseModel):
    pass


class MetaAiChatIn(BaseModel):
    prompt: str = Field(..., description="Prompt or task instructions to execute via Meta AI Muse Spark")
    model: str = Field("muse-spark-1.3", description="Model ID (muse-spark-1.3, muse-spark-1.2)")
    max_tokens: int = Field(800, ge=1, le=4096, description="Max tokens for completion")


# --------------------------------------------------------------------------- helpers
def _live_connector(rt: HubRuntime, name: str):
    connector = rt.registry.get(name)
    if rt.mock:
        return connector
    report = connector.report(live_probe=False)
    if report.live_state in (ConnectorState.NEEDS_AUTH, ConnectorState.CONFIG_REQUIRED):
        state, detail = KNOWN_BLOCKERS.get(name, ("NEEDS_AUTH", report.detail))
        raise ToolUnavailable(str(state), detail)
    if report.live_state == ConnectorState.NEEDS_ACCESS:
        raise ToolUnavailable("NEEDS_API_ACCESS", report.detail)
    return connector


def _dump(records: list[Any]) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in records]


def _push_to_shared_drive(rt: HubRuntime, local_path: Any) -> str | None:
    """Best-effort mirror of a local artifact to a shared drive so colleagues can open it
    without this machine. Tries Google Drive first, then OneDrive (M365), whichever is
    actually configured. Never raises: a sharing failure must not fail the tool call that
    produced the artifact.
    """
    if rt.mock:
        return None
    remote_path = f"{local_path.parent.name}/{local_path.name}"
    for connector_name in ("google_drive", "m365"):
        try:
            connector = rt.registry.get(connector_name)
        except KeyError:
            continue
        try:
            if connector.report(live_probe=False).live_state not in (ConnectorState.CONNECTED, ConnectorState.DEGRADED):
                continue
            if connector_name == "google_drive":
                result = connector.upload_shared_file(local_path.name, local_path.read_bytes())
            else:
                result = connector.upload_shared_file(remote_path, local_path.read_bytes())
            url = result.get("web_url")
            if url:
                return url
        except Exception:
            continue
    return None


def _artifact(rt: HubRuntime, kind: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    folder = rt.artifacts_dir / (rt.ctx.workflow_id or rt.ctx.correlation_id)
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^0-9A-Za-z]+", "-", name).strip("-")[:60] or kind
    path = folder / f"{kind}-{slug}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    result = {"artifact": str(path.relative_to(rt.settings.data_dir)), **payload}
    shared_url = _push_to_shared_drive(rt, path)
    if shared_url:
        result["shared_url"] = shared_url
    return result


def _norm(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"^https?://", "", value).removeprefix("www.").split("/")[0]
    return re.sub(r"\s+", " ", value)


# --------------------------------------------------------------------------- handlers
def system_status(args: StatusIn, rt: HubRuntime) -> list[dict[str, Any]]:
    from ..workflows.store import WorkflowStore as _S

    store = _S(rt.settings.data_dir / "marketing.db")
    return [connector_status(c, rt.settings, store, live_probe=args.live_probe).model_dump()
            for c in rt.registry._connectors.values()]


def _crm_list(resource: str):
    def handler(args: LimitIn, rt: HubRuntime) -> list[dict[str, Any]]:
        connector = _live_connector(rt, "zoho")
        if rt.mock:
            if resource == "accounts":
                return mock_crm_accounts()[: args.limit]
            return [r for r in connector.mock_search(resource, limit=args.limit)]
        from ..connectors.zoho_delegate import ZohoDelegateError, ZohoSessionExpired

        try:
            return _dump(connector.read(resource, limit=args.limit, correlation_id=rt.ctx.correlation_id))
        except ZohoSessionExpired as exc:
            raise ToolUnavailable("NEEDS_AUTH", str(exc)) from None
        except ZohoDelegateError as exc:
            raise ToolUnavailable("DEGRADED", f"Zoho via Claude Code failed: {exc}") from None

    return handler


def crm_find_existing(args: FindExistingIn, rt: HubRuntime) -> dict[str, Any]:
    connector = _live_connector(rt, "zoho")
    if rt.mock:
        accounts = mock_crm_accounts()
        names = {_norm(str(a["Account_Name"])): str(a["id"]) for a in accounts}
        domains = {_norm(str(a["Website"])): str(a["id"]) for a in accounts}
        scanned = len(accounts)
    else:
        rows = _dump(connector.read("accounts", limit=200, correlation_id=rt.ctx.correlation_id))
        names = {_norm(r.get("name") or ""): r.get("external_id") for r in rows if r.get("name")}
        domains = {_norm(r.get("domain") or ""): r.get("external_id") for r in rows if r.get("domain")}
        scanned = len(rows)
    matches = {}
    for company in args.companies:
        if _norm(company) in names:
            matches[company] = names[_norm(company)]
    for domain in args.domains:
        if _norm(domain) in domains:
            matches[domain] = domains[_norm(domain)]
    return {"matches": matches, "accounts_scanned": scanned, "bounded": scanned >= 200}


def crm_propose_task(args: TaskIn, rt: HubRuntime) -> dict[str, Any]:
    proposal = TaskProposal(subject=args.subject, related_company=args.related_company, due_in_days=args.due_in_days,
                            owner_hint=args.owner_hint, reason=args.reason, environment=rt.settings.environment)
    return _artifact(rt, "task-proposal", args.related_company, proposal.model_dump(mode="json"))


def crm_create_task(args: TaskIn, rt: HubRuntime) -> dict[str, Any]:
    _live_connector(rt, "zoho")
    if rt.mock:
        return {"id": f"mock-task-{abs(hash(args.subject)) % 10_000}", "subject": args.subject, "label": "SYNTHETIC_MOCK_DATA"}
    raise NotImplementedError("Zoho writes are not enabled: connector is LIVE_READ only.")


def crm_delete_record(args: DeleteRecordIn, rt: HubRuntime) -> dict[str, Any]:
    raise NotImplementedError("CRM deletion is never automated.")


def prospecting_search_companies(args: SearchCompaniesIn, rt: HubRuntime) -> list[dict[str, Any]]:
    _live_connector(rt, "apollo")
    if rt.mock:
        leads = mock_logistics_leads(rt.ctx.correlation_id, limit=min(args.limit, 4))
        return [LeadCandidate(company=l.metadata["company"], domain=l.metadata["domain"], contact_name=l.full_name,
                              title=l.title, source="mock_apollo", environment=l.environment, synthetic=True,
                              score_reason=l.score_reason).model_dump(mode="json") for l in leads]
    connector = rt.registry.get("apollo")
    keywords = args.keywords or [args.industry]
    rows = connector.search_companies(keywords, [args.location], per_page=args.limit)
    seen, out = set(), []
    for org in rows:
        name = org.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        industry = org.get("industry") or ""
        out.append(LeadCandidate(
            company=name, domain=org.get("primary_domain") or org.get("website_url"), source="apollo",
            environment=rt.settings.environment, synthetic=False,
            score_reason=", ".join(x for x in (industry, org.get("city"), str(org.get("estimated_num_employees") or "")) if x),
            source_reference=org.get("linkedin_url") or org.get("website_url"),
        ).model_dump(mode="json"))
    return out[: args.limit]


def prospecting_search_people(args: SearchPeopleIn, rt: HubRuntime) -> list[dict[str, Any]]:
    connector = _live_connector(rt, "apollo")
    if rt.mock:
        return connector.mock_search("people", limit=args.limit)
    raise NotImplementedError("Apollo people search lands in milestone 9.")


def email_get_unread_count(args: NoInput, rt: HubRuntime) -> dict[str, Any]:
    _live_connector(rt, "m365")
    if rt.mock:
        return {"unread": 7, "label": "SYNTHETIC_MOCK_DATA"}
    raise NotImplementedError("Outlook unread count lands in milestone 10.")


def email_create_draft(args: EmailDraftIn, rt: HubRuntime) -> dict[str, Any]:
    _live_connector(rt, "m365")
    draft = EmailDraft(to_name=args.to_name, to_email=args.to_email, subject=args.subject, body=args.body,
                       lead_company=args.lead_company, environment=rt.settings.environment)
    if rt.mock:
        return _artifact(rt, "email-draft", args.lead_company, draft.model_dump(mode="json"))
    raise NotImplementedError("Outlook draft creation lands in milestone 10.")


def email_send(args: SendEmailIn, rt: HubRuntime) -> dict[str, Any]:
    raise NotImplementedError("Sending email is disabled in this phase.")


def files_search_documents(args: SearchDocsIn, rt: HubRuntime) -> list[dict[str, Any]]:
    # Ưu tiên tìm kiếm trên Google Drive kết nối trực tiếp
    try:
        drive_connector = rt.registry.get("google_drive")
        if drive_connector:
            return drive_connector.search_files(query=args.query, limit=args.limit)
    except Exception:
        pass
    try:
        connector = _live_connector(rt, "m365")
        if rt.mock:
            return connector.mock_search(args.query, limit=args.limit)
    except Exception:
        pass
    return []


def files_read_document(args: ReadDocIn, rt: HubRuntime) -> dict[str, Any]:
    drive_connector = rt.registry.get("google_drive")
    if not drive_connector:
        raise ToolUnavailable("NOT_CONFIGURED", "Google Drive connector không khả dụng.")
    return drive_connector.read_file_content(args.file_id, max_chars=args.max_chars)



def website_get_metadata(args: NoInput, rt: HubRuntime) -> list[dict[str, Any]]:
    connector = _live_connector(rt, "website")
    return _dump(connector.read("metadata", limit=1, correlation_id=rt.ctx.correlation_id))


def website_get_recent_content(args: LimitIn, rt: HubRuntime) -> dict[str, Any]:
    connector = _live_connector(rt, "website")
    if rt.mock:
        return {"stack": "mock", "items": connector.mock_search("posts", limit=args.limit)}
    base = (connector.env("WEBSITE_URL") or "").rstrip("/")
    response = connector.request("GET", f"{base}/wp-json/wp/v2/posts",
                                 params={"per_page": min(args.limit, 20), "_fields": "id,date,link,title"},
                                 timeout=20.0, follow_redirects=True)
    if response.status_code == 404:
        raise ToolUnavailable("NOT_CONFIGURED", "Site exposes no WordPress REST API; stack adapter not chosen yet.")
    response.raise_for_status()
    items = [{"id": p.get("id"), "date": p.get("date"), "url": p.get("link"),
              "title": (p.get("title") or {}).get("rendered")} for p in response.json()]
    return {"stack": "wordpress-rest", "total": response.headers.get("x-wp-total"), "items": items}


def social_get_recent_videos(args: LimitIn, rt: HubRuntime) -> list[dict[str, Any]]:
    connector = _live_connector(rt, "youtube")
    return _dump(connector.read("recent_videos", limit=min(args.limit, 50), correlation_id=rt.ctx.correlation_id))


def social_get_channel_metrics(args: NoInput, rt: HubRuntime) -> dict[str, Any]:
    connector = _live_connector(rt, "youtube")
    if rt.mock:
        return {"subscribers": 1234, "views": 5678, "videos": 3, "label": "SYNTHETIC_MOCK_DATA"}
    channel = connector.env("YOUTUBE_CHANNEL_ID")
    if not channel:
        raise ToolUnavailable("NOT_CONFIGURED", "YOUTUBE_CHANNEL_ID missing")
    response = connector.request("GET", "https://www.googleapis.com/youtube/v3/channels",
                                 params={"part": "statistics,snippet", "id": channel},
                                 headers={"x-goog-api-key": connector.env("YOUTUBE_API_KEY") or ""}, timeout=15.0)
    response.raise_for_status()
    items = response.json().get("items") or []
    if not items:
        raise ToolUnavailable("ERROR", "Channel not found")
    stats, snippet = items[0].get("statistics", {}), items[0].get("snippet", {})
    return {"channel": snippet.get("title"), "subscribers": int(stats.get("subscriberCount", 0)),
            "views": int(stats.get("viewCount", 0)), "videos": int(stats.get("videoCount", 0))}


def social_publish_post(args: PublishPostIn, rt: HubRuntime) -> dict[str, Any]:
    if rt.mock:
        return {"channel": args.channel, "status": "published", "post_id": f"mock_{args.channel}_001",
                "text": args.text, "label": "SYNTHETIC_MOCK_DATA"}
    if args.channel in ("facebook", "meta"):
        connector = rt.registry.get("meta_ads")
        if not connector.page_configured():
            raise ToolUnavailable("NOT_CONFIGURED", "META_PAGE_ACCESS_TOKEN / META_PAGE_ID missing.")
        return connector.publish_page_post(args.text)
    elif args.channel == "tiktok":
        connector = _live_connector(rt, "tiktok")
        from pathlib import Path
        file_path = args.text.strip()
        title = "Minh Van Logistics Video"
        if not Path(file_path).is_file():
            default_vid = Path(r"C:\Users\Admin\minhvan-tiktok-tt01\minhvan_tt01_final.mp4")
            if default_vid.is_file():
                title = file_path
                file_path = str(default_vid)
            else:
                raise FileNotFoundError(f"Video file not found for TikTok publish: {args.text}")
        return connector.upload_video_file(file_path=file_path, title=title, publish_mode="auto")
    else:
        raise NotImplementedError(f"Publishing to channel '{args.channel}' is not enabled or requires product approval.")


def social_create_page_post_draft(args: PagePostDraftIn, rt: HubRuntime) -> dict[str, Any]:
    if rt.mock:
        return _artifact(rt, "facebook-page-post-draft", "draft",
                         {"message": args.message, "status": "draft", "published": False, "label": "SYNTHETIC_MOCK_DATA"})
    # Page posting only needs META_PAGE_ACCESS_TOKEN/META_PAGE_ID, not the ad-account
    # credentials that _live_connector's report()-based gate requires, so check that
    # directly instead of routing through the ads-account readiness check.
    connector = rt.registry.get("meta_ads")
    if not connector.page_configured():
        raise ToolUnavailable("NOT_CONFIGURED", "META_PAGE_ACCESS_TOKEN / META_PAGE_ID missing.")
    return connector.create_page_post_draft(args.message)


def tiktok_get_channel_metrics(args: NoInput, rt: HubRuntime) -> dict[str, Any]:
    connector = _live_connector(rt, "tiktok")
    if rt.mock:
        return {"channel": "Buzz Marketing Hub", "followers": 2450, "likes": 18200, "videos": 12, "label": "SYNTHETIC_MOCK_DATA"}
    return connector.get_channel_metrics()


def tiktok_get_recent_videos(args: LimitIn, rt: HubRuntime) -> list[dict[str, Any]]:
    connector = _live_connector(rt, "tiktok")
    if rt.mock:
        return connector.mock_search("videos", limit=args.limit)
    return connector.get_recent_videos(limit=args.limit)


def tiktok_upload_video_draft(args: TikTokDraftIn, rt: HubRuntime) -> dict[str, Any]:
    connector = _live_connector(rt, "tiktok")
    if rt.mock:
        return _artifact(rt, "tiktok-video-draft", args.title,
                         {"title": args.title, "video_source": args.video_source, "privacy_level": args.privacy_level,
                          "status": "draft_inbox", "published": False, "label": "SYNTHETIC_MOCK_DATA"})
    from pathlib import Path
    source_path = Path(args.video_source.strip())
    if not source_path.is_file():
        default_vid = Path(r"C:\Users\Admin\minhvan-tiktok-tt01\minhvan_tt01_final.mp4")
        if default_vid.is_file():
            source_path = default_vid
    if source_path.is_file():
        return connector.upload_video_file(
            file_path=str(source_path),
            title=args.title,
            privacy_level=args.privacy_level,
            publish_mode="inbox",
        )
    return {"status": "staged_draft", "title": args.title, "privacy_level": args.privacy_level, "video_source": args.video_source}


def ads_get_campaign_performance(args: AdsPerfIn, rt: HubRuntime) -> list[dict[str, Any]]:
    _live_connector(rt, "meta_ads" if args.platform == "meta" else "google_ads")
    if rt.mock:
        return mock_campaign_metrics()
    raise NotImplementedError("Ads read lands after Meta/Google API access.")


def ads_launch_campaign(args: LaunchCampaignIn, rt: HubRuntime) -> dict[str, Any]:
    raise NotImplementedError("Campaign launch is never automated in this phase.")


def ads_change_budget(args: ChangeBudgetIn, rt: HubRuntime) -> dict[str, Any]:
    raise NotImplementedError("Budget changes are never automated in this phase.")


def content_save_draft(args: ContentDraftIn, rt: HubRuntime) -> dict[str, Any]:
    return _artifact(rt, "content-draft", args.title,
                     {"title": args.title, "channel": args.channel, "body": args.body, "status": "draft",
                      "environment": rt.settings.environment.value})


def analytics_snapshot(args: NoInput, rt: HubRuntime) -> dict[str, Any]:
    """Collect only metrics that a live (or mock) source can back. Missing ones are listed, not invented."""
    metrics: list[MetricSnapshot] = []
    unavailable: dict[str, str] = {}
    for label, fn, source in (("youtube", lambda: social_get_channel_metrics(NoInput(), rt), "youtube"),
                              ("website", lambda: website_get_recent_content(LimitIn(limit=1), rt), "website"),
                              ("crm_leads", lambda: _crm_list("leads")(LimitIn(limit=200), rt), "zoho")):
        try:
            data = fn()
        except ToolUnavailable as exc:
            unavailable[label] = exc.state
            continue
        except Exception as exc:
            unavailable[label] = type(exc).__name__
            continue
        if label == "youtube":
            for key in ("subscribers", "views", "videos"):
                metrics.append(MetricSnapshot(name=f"youtube_{key}", value=data[key], source=source))
        elif label == "website" and data.get("total") is not None:
            metrics.append(MetricSnapshot(name="website_posts_total", value=int(data["total"]), source=source))
        elif label == "crm_leads":
            metrics.append(MetricSnapshot(name="crm_leads_visible", value=len(data), source=source,
                                          note="bounded to 200; profile visibility may hide records"))
    return {"as_of": datetime.now(timezone.utc).isoformat(), "metrics": [m.model_dump(mode="json") for m in metrics],
            "unavailable": unavailable, "environment": rt.settings.environment.value}


def codex_run(inp: CodexRunIn, rt: HubRuntime) -> dict[str, Any]:
    control_js = "C:\\Users\\Admin\\AppData\\Local\\agy\\bin\\codex-control.js"
    cmd = ["node", control_js, "exec", inp.prompt, "--cd", inp.cwd, "--json"]
    if inp.model:
        cmd.extend(["--model", inp.model])

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0 and proc.stdout:
            try:
                res = json.loads(proc.stdout)
                return {
                    "status": "OK" if res.get("exitCode") == 0 else "ERROR",
                    "exit_code": res.get("exitCode", 0),
                    "stdout": (res.get("stdout") or "").strip(),
                    "stderr": (res.get("stderr") or "").strip(),
                    "prompt": inp.prompt,
                }
            except Exception:
                pass
        return {
            "status": "OK" if proc.returncode == 0 else "ERROR",
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip() if proc.returncode != 0 else "",
            "prompt": inp.prompt,
        }
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": "Codex execution timed out after 180s", "prompt": inp.prompt}
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "prompt": inp.prompt}



def codex_open(inp: CodexOpenIn, rt: HubRuntime) -> dict[str, Any]:
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Start-Process 'shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App'"]
        subprocess.run(cmd, capture_output=True, timeout=10)
        return {"status": "OK", "message": "Codex Desktop App launch signal sent successfully."}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def codex_status(inp: CodexStatusIn, rt: HubRuntime) -> dict[str, Any]:
    codex_bin = "C:\\Users\\Admin\\.codex\\packages\\standalone\\current\\bin\\codex.exe"
    cli_exists = Path(codex_bin).exists()

    desktop_app_running = False
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-Process -Name ChatGPT, codex -ErrorAction SilentlyContinue).Count"],
            capture_output=True, text=True, timeout=5,
        )
        count = int(res.stdout.strip() or "0")
        desktop_app_running = count > 0
    except Exception:
        pass

    daemon_running = False
    daemon_info = {}
    if cli_exists:
        try:
            d_res = subprocess.run(
                [codex_bin, "app-server", "daemon", "version"],
                capture_output=True, text=True, timeout=5,
            )
            if d_res.returncode == 0 and d_res.stdout:
                daemon_running = True
                try:
                    daemon_info = json.loads(d_res.stdout)
                except Exception:
                    daemon_info = {"raw": d_res.stdout.strip()}
        except Exception:
            pass

    return {
        "status": "OK",
        "cli_installed": cli_exists,
        "cli_path": codex_bin,
        "desktop_app_running": desktop_app_running,
        "daemon_running": daemon_running,
        "daemon_details": daemon_info,
    }


def meta_ai_chat(inp: MetaAiChatIn, rt: HubRuntime) -> dict[str, Any]:
    connector = rt.registry.get("meta_ai")
    try:
        messages = [{"role": "user", "content": inp.prompt}]
        res = connector.chat_completion(messages=messages, model=inp.model, max_tokens=inp.max_tokens)
        text = res.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"status": "OK", "model": inp.model, "output": text, "raw": res}
    except Exception as exc:
        return {"status": "ERROR", "model": inp.model, "error": str(exc)}


def meta_ai_models(inp: NoInput, rt: HubRuntime) -> dict[str, Any]:
    connector = rt.registry.get("meta_ai")
    try:
        models = connector.list_models()
        return {"status": "OK", "models": [m.get("id") for m in models], "details": models}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)}


# --------------------------------------------------------------------------- registry
def _spec(name, impact, connector, capability, model, description, summarize=None) -> ToolSpec:
    return ToolSpec(name=name, impact=impact, connector=connector, capability=capability, input_model=model,
                    description=description, summarize=summarize)


CATALOG: list[tuple[ToolSpec, Any]] = [
    (_spec("system.connector_status", Impact.READ, "system", "status", StatusIn,
           "Per-capability state (AUTH/READ/ANALYTICS/DRAFT/PUBLISH) for every connector."), system_status),
    (_spec("crm.search_leads", Impact.READ, "zoho", "read_crm_records", LimitIn, "List Zoho CRM leads."), _crm_list("leads")),
    (_spec("crm.list_contacts", Impact.READ, "zoho", "read_crm_records", LimitIn, "List Zoho CRM contacts."), _crm_list("contacts")),
    (_spec("crm.list_accounts", Impact.READ, "zoho", "read_crm_records", LimitIn, "List Zoho CRM accounts."), _crm_list("accounts")),
    (_spec("crm.list_deals", Impact.READ, "zoho", "read_crm_records", LimitIn, "List Zoho CRM deals."), _crm_list("deals")),
    (_spec("crm.list_tasks", Impact.READ, "zoho", "read_crm_records", LimitIn, "List Zoho CRM tasks."), _crm_list("tasks")),
    (_spec("crm.find_existing", Impact.READ, "zoho", "read_crm_records", FindExistingIn,
           "Check which companies/domains already exist as Zoho accounts (dedupe)."), crm_find_existing),
    (_spec("crm.propose_task", Impact.DRAFT, "local", "task_proposal", TaskIn,
           "Save a Sales task proposal locally. Does not write Zoho."), crm_propose_task),
    (_spec("crm.create_task", Impact.WRITE_LOW_RISK, "zoho", "create_or_update_record", TaskIn,
           "Create a task in Zoho CRM (requires approval).",
           lambda p: f"Tạo task Zoho: '{p['subject']}' cho {p['related_company']} (hạn +{p['due_in_days']} ngày)"), crm_create_task),
    (_spec("crm.delete_record", Impact.HIGH_IMPACT, "zoho", "delete_record", DeleteRecordIn,
           "Delete a Zoho record (always blocked).", lambda p: f"XOÁ {p['module']} {p['record_id']} trong Zoho"), crm_delete_record),
    (_spec("prospecting.search_companies", Impact.READ, "apollo", "organization_search", SearchCompaniesIn,
           "Find companies matching an ICP (Apollo)."), prospecting_search_companies),
    (_spec("prospecting.search_people", Impact.READ, "apollo", "people_search", SearchPeopleIn,
           "Find people by title at given domains (Apollo)."), prospecting_search_people),
    (_spec("email.get_unread_count", Impact.READ, "m365", "read_mail_metadata", NoInput, "Unread Outlook count."), email_get_unread_count),
    (_spec("email.create_draft", Impact.DRAFT, "m365", "create_email_draft", EmailDraftIn,
           "Create an Outlook draft (never sends)."), email_create_draft),
    (_spec("email.send", Impact.HIGH_IMPACT, "m365", "send_email", SendEmailIn, "Send an email (approval + phase gate).",
           lambda p: f"GỬI email tới {p['to_email']}: '{p['subject']}'"), email_send),
    (_spec("files.search_documents", Impact.READ, "google_drive", "search_files", SearchDocsIn, "Tìm kiếm tệp trên Google Drive theo tên hoặc nội dung."), files_search_documents),
    (_spec("files.read_document", Impact.READ, "google_drive", "read_file", ReadDocIn, "Đọc nội dung văn bản, Google Docs, hoặc bảng tính Google Sheets từ Google Drive."), files_read_document),
    (_spec("website.get_metadata", Impact.READ, "website", "read_public_metadata", NoInput, "Website title/description."), website_get_metadata),
    (_spec("website.get_recent_content", Impact.READ, "website", "read_public_metadata", LimitIn,
           "Latest published posts (stack auto-detected)."), website_get_recent_content),
    (_spec("social.get_recent_videos", Impact.READ, "youtube", "read_public_channel_video_metadata", LimitIn,
           "Latest YouTube videos on the company channel."), social_get_recent_videos),
    (_spec("social.get_channel_metrics", Impact.READ, "youtube", "read_public_channel_video_metadata", NoInput,
           "YouTube channel subscribers/views/videos."), social_get_channel_metrics),
    (_spec("social.publish_post", Impact.HIGH_IMPACT, "linkedin", "publish_post", PublishPostIn,
           "Publish a social post (approval + phase gate).", lambda p: f"ĐĂNG bài lên {p['channel']}: {p['text'][:120]}"), social_publish_post),
    (_spec("social.create_facebook_page_post_draft", Impact.DRAFT, "meta_ads", "create_page_post_draft", PagePostDraftIn,
           "Create an unpublished Facebook Page post draft (published=false; never public)."), social_create_page_post_draft),
    (_spec("tiktok.get_channel_metrics", Impact.READ, "tiktok", "read_channel_metrics", NoInput,
           "TikTok account followers, following, likes, and video count."), tiktok_get_channel_metrics),
    (_spec("tiktok.get_recent_videos", Impact.READ, "tiktok", "read_recent_videos", LimitIn,
           "Latest published TikTok videos with views, likes, comments, and shares."), tiktok_get_recent_videos),
    (_spec("tiktok.upload_video_draft", Impact.DRAFT, "tiktok", "upload_video_draft", TikTokDraftIn,
           "Stage or upload a video draft to TikTok inbox (never public)."), tiktok_upload_video_draft),
    (_spec("ads.get_campaign_performance", Impact.READ, "meta_ads", "read_ad_metrics", AdsPerfIn,
           "Campaign spend/impressions/clicks/conversions."), ads_get_campaign_performance),
    (_spec("ads.launch_campaign", Impact.HIGH_IMPACT, "meta_ads", "launch_or_modify_campaign", LaunchCampaignIn,
           "Launch a paid campaign (approval + phase gate).",
           lambda p: f"CHẠY chiến dịch {p['platform']} '{p['name']}' {p['daily_budget_vnd']:,} VND/ngày"), ads_launch_campaign),
    (_spec("ads.change_budget", Impact.HIGH_IMPACT, "meta_ads", "change_budget", ChangeBudgetIn,
           "Change ad budget (approval + phase gate).",
           lambda p: f"ĐỔI ngân sách {p['platform']} {p['campaign_id']} → {p['new_daily_budget_vnd']:,} VND/ngày"), ads_change_budget),
    (_spec("content.save_draft", Impact.DRAFT, "local", "artifact", ContentDraftIn, "Save a content draft artifact."), content_save_draft),
    (_spec("analytics.snapshot", Impact.READ, "multi", "metrics", NoInput,
           "Source-backed KPI snapshot; lists metrics that are unavailable instead of guessing."), analytics_snapshot),
    (_spec("codex.run", Impact.READ, "codex", "run", CodexRunIn,
           "Execute a prompt or task using the local OpenAI Codex Desktop App/CLI and return the result."), codex_run),
    (_spec("codex.open", Impact.READ, "codex", "open", CodexOpenIn,
           "Launch and bring the OpenAI Codex Desktop App to front on Windows."), codex_open),
    (_spec("codex.status", Impact.READ, "codex", "status", CodexStatusIn,
           "Check status of the local OpenAI Codex Desktop App, CLI, and App-Server daemon."), codex_status),
    (_spec("meta_ai.chat", Impact.READ, "meta_ai", "chat_completion", MetaAiChatIn,
           "Generate reasoning, copy, or strategy using Meta AI Muse Spark from dev.meta.ai."), meta_ai_chat),
    (_spec("meta_ai.models", Impact.READ, "meta_ai", "list_models", NoInput,
           "List available Meta AI models from dev.meta.ai."), meta_ai_models),
]


def build_hub(settings: Settings | None = None, store: WorkflowStore | None = None,
              approvals: ApprovalEngine | None = None, policy: PolicyEngine | None = None) -> ToolHub:
    settings = settings or Settings.from_env()
    settings.ensure_runtime_dirs()
    store = store or WorkflowStore(settings.data_dir / "marketing.db")
    approvals = approvals or ApprovalEngine(store, [BuzzSignedEventVerifier(settings.owner_pubkey)])
    hub = ToolHub(settings, ConnectorRegistry(settings), store, approvals, policy)
    for spec, handler in CATALOG:
        hub.register(spec, handler)
    return hub

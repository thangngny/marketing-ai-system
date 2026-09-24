"""The tool catalog: small, explicit, typed tools grouped by namespace.

Handlers only translate between the canonical model and a connector. They never
decide policy; the hub already did.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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


class PublishPostIn(BaseModel):
    channel: Literal["linkedin", "facebook", "youtube", "tiktok", "zalo"]
    text: str = Field(min_length=10, max_length=3000)


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


def _artifact(rt: HubRuntime, kind: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    folder = rt.artifacts_dir / (rt.ctx.workflow_id or rt.ctx.correlation_id)
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^0-9A-Za-z]+", "-", name).strip("-")[:60] or kind
    path = folder / f"{kind}-{slug}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"artifact": str(path.relative_to(rt.settings.data_dir)), **payload}


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
    raise NotImplementedError("Apollo organization search lands in milestone 9.")


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
    connector = _live_connector(rt, "m365")
    if rt.mock:
        return connector.mock_search(args.query, limit=args.limit)
    raise NotImplementedError("OneDrive/SharePoint search lands in milestone 10.")


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
    raise NotImplementedError("Publishing is disabled in this phase.")


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
    (_spec("files.search_documents", Impact.READ, "m365", "read_files", SearchDocsIn, "Search OneDrive/SharePoint."), files_search_documents),
    (_spec("website.get_metadata", Impact.READ, "website", "read_public_metadata", NoInput, "Website title/description."), website_get_metadata),
    (_spec("website.get_recent_content", Impact.READ, "website", "read_public_metadata", LimitIn,
           "Latest published posts (stack auto-detected)."), website_get_recent_content),
    (_spec("social.get_recent_videos", Impact.READ, "youtube", "read_public_channel_video_metadata", LimitIn,
           "Latest YouTube videos on the company channel."), social_get_recent_videos),
    (_spec("social.get_channel_metrics", Impact.READ, "youtube", "read_public_channel_video_metadata", NoInput,
           "YouTube channel subscribers/views/videos."), social_get_channel_metrics),
    (_spec("social.publish_post", Impact.HIGH_IMPACT, "linkedin", "publish_post", PublishPostIn,
           "Publish a social post (approval + phase gate).", lambda p: f"ĐĂNG bài lên {p['channel']}: {p['text'][:120]}"), social_publish_post),
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

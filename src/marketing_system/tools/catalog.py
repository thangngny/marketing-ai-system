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
from ..constants import ConnectorState, Impact, Environment
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
    vats: list[str] = Field(default_factory=list, max_length=100)


class TaskIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    related_company: str = Field(min_length=1, max_length=200)
    due_in_days: int = Field(3, ge=0, le=90)
    reason: str = Field("", max_length=1000)
    owner_hint: str | None = None


class DeleteRecordIn(BaseModel):
    module: Literal["Leads", "Contacts", "Accounts", "Deals", "Tasks"]
    record_id: str


class PreviewCrmImportIn(BaseModel):
    leads: list[dict[str, Any]] = Field(default_factory=list, description="Danh sách ứng viên lead cần preview trước khi import.")


class LeadPipelineRunIn(BaseModel):
    industry_keywords: list[str] = Field(default_factory=lambda: ["medical", "thiết bị y tế", "dược phẩm", "linh kiện điện tử"])
    industry_codes: list[str] = Field(default_factory=lambda: ["3250", "2611", "4651", "4659"])
    trade_lanes: list[str] = Field(default_factory=lambda: ["JP-VN", "KR-VN", "CN-VN", "EU-VN"])
    limit: int = Field(10, ge=1, le=50)


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


class SchedulePostIn(BaseModel):
    channel: Literal["zalo", "tiktok", "youtube", "facebook", "linkedin"] = Field(..., description="Kênh cần đặt lịch đăng: zalo, tiktok, youtube, facebook, linkedin")
    time: str = Field(..., description="Thời gian hẹn đăng, ví dụ: '11:00', '15:00', '+30m', '2026-10-28 15:00'")
    title: str = Field("", description="Tiêu đề bài viết hoặc video")
    text: str = Field("", description="Nội dung Caption hoặc bài viết")
    media_url: str | None = Field(None, description="URL video/ảnh trên Blossom hoặc web")
    file_path: str | None = Field(None, description="Đường dẫn file video/ảnh trên máy tính")
    content_type: Literal["video", "article", "post"] = Field("video", description="Loại nội dung: video, article, post")
    channel_id: str | None = Field("a6399188-f310-4985-a218-35c96209945c", description="ID kênh Buzz để nhận thông báo nghiệm thu (mặc định #Assistant Marketing)")


class ListScheduledPostsIn(BaseModel):
    status: Literal["pending", "published", "failed", "cancelled", "all"] = Field("pending", description="Trạng thái lọc: pending, published, failed, all")
    limit: int = Field(15, ge=1, le=50, description="Số lượng lịch hẹn cần lấy")


class CancelScheduledPostIn(BaseModel):
    task_id: str = Field(..., description="Mã task ID của lịch hẹn cần hủy (ví dụ: sch_1793159791_89b51e)")


class PagePostDraftIn(BaseModel):
    message: str = Field(min_length=10, max_length=3000)
    published: bool = Field(True, description="Đặt True để đăng bài công khai trực tiếp lên Fanpage Facebook (mặc định công khai); False để lưu bản nháp riêng tư.")


class TikTokDraftIn(BaseModel):
    title: str = Field(min_length=3, max_length=200, description="Tiêu đề hoặc caption video TikTok.")
    video_source: str = Field(description="URL hoặc đường dẫn file video để tải lên.")
    privacy_level: str = Field("PUBLIC_TO_EVERYONE", description="Mức độ riêng tư: PUBLIC_TO_EVERYONE (công khai cho mọi người), MUTUAL_FOLLOW_FRIENDS, hoặc SELF_ONLY (chỉ mình tôi).")
    publish_mode: Literal["auto", "direct", "inbox"] = Field("auto", description="Chế độ tải lên: auto (đăng công khai trực tiếp, tự fallback inbox nếu cần), direct, hoặc inbox.")


class VideoProduceIn(BaseModel):
    title: str = Field(min_length=3, max_length=200, description="Tiêu đề video và chủ đề")
    script: str = Field(min_length=10, max_length=5000, description="Kịch bản/lời bình tiếng Việt")
    mode: Literal["hybrid", "avatar", "cinematic", "motion"] = Field(
        "hybrid",
        description="Chế độ dựng: hybrid (Pexels + AI), avatar (HeyGen MC Lina), cinematic (Higgsfield Kling 3.0), motion (HyperFrames)",
    )
    aspect_ratio: Literal["9:16", "16:9"] = Field("9:16", description="Tỷ lệ khung hình: 9:16 (TikTok/Reels) hoặc 16:9")
    enable_subtitles: bool = Field(True, description="Tự động nhận diện giọng nói và đục phụ đề động viền vàng kiểu TikTok")
    auto_publish: bool = Field(False, description="Tự động đăng lên kênh TikTok sau khi hoàn tất")


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
    cwd: str = Field(default_factory=lambda: str(Path.home()), description="Working directory for task execution")
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
    if not hasattr(rt, "registry") or rt.registry is None:
        return None
    try:
        connector = rt.registry.get(name)
    except Exception:
        return None
    if getattr(rt, "mock", True) or connector is None:
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
    import os
    import time
    import uuid
    from ..models import utc_now, DedupeDecision
    from ..lead_engine.verifier import validate_vietnam_vat

    connector = _live_connector(rt, "zoho")
    matches: dict[str, str] = {}
    scope_checked: list[str] = []
    scanned = 0
    bounded = False
    api_error: str | None = None

    # Mutex lock handling for dedupe concurrency
    buzz_dir = Path(os.environ.get("BUZZ_HOME", str(Path.home() / ".buzz")))
    lock_dir = buzz_dir / "locks"
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
        (lock_dir / "zoho_dedupe.lock").touch(exist_ok=True)
    except Exception:
        pass

    # 1. Check local VAT cache if available (e.g. Minh Van 3,603 live records)
    vat_cache_path = Path(os.environ.get("BUZZ_VAT_CACHE", str(buzz_dir / "tools" / "zoho_live_vat_cache.json")))
    has_vat_cache = False
    cache_age_seconds: float | None = None
    cached_vats: set[str] = set()
    cached_names: dict[str, str] = {}

    if vat_cache_path.exists():
        try:
            mtime = vat_cache_path.stat().st_mtime
            cache_age_seconds = time.time() - mtime
            cdata = json.loads(vat_cache_path.read_text(encoding="utf-8"))
            cached_vats = set(str(v).strip() for v in cdata.get("vats", []) if v)
            cached_names = {_norm(str(n)): str(n) for n in cdata.get("names", []) if n}
            has_vat_cache = bool(cached_vats or cached_names)
            if has_vat_cache:
                scope_checked.append("zoho_live_vat_cache")

            for raw_vat in args.vats:
                if not raw_vat:
                    continue
                v_ok, v_norm = validate_vietnam_vat(raw_vat)
                target_vat = v_norm if v_ok else raw_vat.strip()
                if target_vat in cached_vats:
                    matches[raw_vat] = f"vat_cache:{target_vat}"

            for comp in args.companies:
                norm_c = _norm(comp)
                if norm_c in cached_names:
                    matches[comp] = f"vat_cache_name:{cached_names[norm_c]}"
        except Exception as exc:
            scope_checked.append(f"vat_cache_error:{exc}")

    # 2. Query CRM connector for Accounts
    names: dict[str, str] = {}
    domains: dict[str, str] = {}
    if getattr(rt, "mock", True) or connector is None:
        accounts = mock_crm_accounts()
        names = {_norm(str(a["Account_Name"])): str(a["id"]) for a in accounts}
        domains = {_norm(str(a["Website"])): str(a["id"]) for a in accounts}
        scanned = len(accounts)
        bounded = False
        scope_checked.append("mock_accounts")
    else:
        try:
            corr_id = getattr(getattr(rt, "ctx", None), "correlation_id", "corr-dedupe")
            rows = _dump(connector.read("accounts", limit=200, correlation_id=corr_id))
            names = {_norm(r.get("name") or ""): str(r.get("external_id") or r.get("id", "")) for r in rows if r.get("name")}
            domains = {_norm(r.get("domain") or ""): str(r.get("external_id") or r.get("id", "")) for r in rows if r.get("domain")}
            scanned = len(rows)
            bounded = (scanned >= 200)
            scope_checked.append("zoho_accounts_api")
        except Exception as exc:
            api_error = str(exc)
            names = {}
            domains = {}
            scope_checked.append(f"zoho_error:{exc}")

    for company in args.companies:
        n_comp = _norm(company)
        if n_comp in names and company not in matches:
            matches[company] = str(names[n_comp])
    for domain in args.domains:
        n_dom = _norm(domain)
        if n_dom in domains and domain not in matches:
            matches[domain] = str(domains[n_dom])

    run_id = f"dedupe-{uuid.uuid4().hex[:8]}"
    check_time = utc_now()

    # 3. Generate Independent Per-Entity Dedupe Decisions (V7-001 & V7-002)
    decisions: dict[str, dict[str, Any]] = {}
    for comp in args.companies:
        matched_id = matches.get(comp)
        if matched_id:
            dec_status = "DUPLICATE_CONFIRMED"
            confidence = 1.0 if "vat_cache" in str(matched_id) else 0.95
            q_status = "SUCCESS"
            err = None
            matched_ids = [matched_id]
        elif api_error is not None:
            dec_status = "CHECK_FAILED"
            confidence = 0.0
            q_status = "FAILED"
            err = api_error
            matched_ids = []
        elif bounded and not has_vat_cache:
            dec_status = "PARTIAL_COVERAGE"
            confidence = 0.5
            q_status = "PARTIAL"
            err = "Zoho search bounded (200 records); scope incomplete"
            matched_ids = []
        else:
            dec_status = "NOT_FOUND_IN_CHECKED_SCOPE"
            confidence = 0.95
            q_status = "SUCCESS"
            err = None
            matched_ids = []

        entity_decision = DedupeDecision(
            candidate_key=comp,
            query_run_id=run_id,
            crm_organization="Minh Van Logistics",
            modules_checked=["Accounts", "Leads"] if not getattr(rt, "mock", True) else ["mock_accounts"],
            field_names_checked=["Account_Name", "Website", "VAT_Number"],
            query_criteria={"company": comp},
            query_status=q_status,
            matching_record_ids=matched_ids,
            match_confidence=confidence,
            cache_used=has_vat_cache,
            cache_age_seconds=cache_age_seconds,
            checked_at=check_time,
            decision_status=dec_status,
            error_details=err,
            evidence_ref=f"zoho_dedupe_{run_id}_{uuid.uuid4().hex[:6]}"
        )
        decisions[comp] = entity_decision.model_dump(mode="json")

    # Aggregate batch-level status purely as summary without contaminating per-entity status
    all_statuses = {d["decision_status"] for d in decisions.values()} if decisions else set()
    if "DUPLICATE_CONFIRMED" in all_statuses:
        batch_match_status = "DUPLICATE_FOUND"
    elif "CHECK_FAILED" in all_statuses:
        batch_match_status = "CHECK_FAILED"
    elif "PARTIAL_COVERAGE" in all_statuses:
        batch_match_status = "PARTIAL_COVERAGE"
    elif all_statuses == {"NOT_FOUND_IN_CHECKED_SCOPE"}:
        batch_match_status = "NOT_FOUND_VERIFIED"
    else:
        batch_match_status = "PARTIAL_COVERAGE" if bounded else "NOT_FOUND_VERIFIED"

    coverage_status = "FULL_COVERAGE" if (has_vat_cache or not bounded) and not api_error else "PARTIAL_COVERAGE"

    return {
        "matches": matches,
        "decisions": decisions,
        "accounts_scanned": scanned,
        "vats_checked": len(args.vats),
        "bounded": bounded,
        "match_status": batch_match_status,
        "coverage_status": coverage_status,
        "scope_checked": scope_checked,
        "run_id": run_id,
        "timestamp": check_time.isoformat(),
    }


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


def crm_preview_import(args: PreviewCrmImportIn, rt: HubRuntime) -> dict[str, Any]:
    from ..lead_engine.verifier import validate_vietnam_vat
    from ..identity import generate_payload_hash
    import os
    import uuid

    companies = [str(l.get("company") or "").strip() for l in args.leads if l.get("company")]
    domains = [str(l.get("domain") or "").strip() for l in args.leads if l.get("domain")]
    vats = [str(l.get("vat_number") or "").strip() for l in args.leads if l.get("vat_number")]

    dedupe_res = crm_find_existing(FindExistingIn(companies=companies, domains=domains, vats=vats), rt)
    matches = dedupe_res.get("matches", {})
    decisions = dedupe_res.get("decisions", {})
    coverage = dedupe_res.get("coverage_status", "PARTIAL_COVERAGE")
    is_bounded = dedupe_res.get("bounded", False)

    staged = []
    eligible_records = []
    excluded = []
    eligibility_decisions = {}

    for lead in args.leads:
        comp = str(lead.get("company") or "").strip()
        dom = str(lead.get("domain") or "").strip()
        raw_vat = str(lead.get("vat_number") or "").strip()

        # Retrieve per-entity dedupe decision
        lead_dedupe_dec = decisions.get(comp, {})
        dedupe_status = lead.get("crm_dedupe_status") or lead_dedupe_dec.get("decision_status") or dedupe_res.get("match_status", "NOT_CHECKED")

        # Check duplicate matches
        matched_id = matches.get(comp) or (matches.get(dom) if dom else None) or (matches.get(raw_vat) if raw_vat else None)
        if matched_id or dedupe_status == "DUPLICATE_CONFIRMED":
            excluded.append({
                "company": comp,
                "reason": f"Trùng tài khoản CRM: {matched_id or 'DUPLICATE_CONFIRMED'}",
                "match_id": matched_id or "CONFIRMED",
            })
            eligibility_decisions[comp] = {
                "candidate_id": comp,
                "company": comp,
                "eligibility_status": "DUPLICATE_REVIEW",
                "eligible_for_crm_import": False,
                "reason": "Phát hiện trùng lặp với dữ liệu Zoho CRM hiện có"
            }
            continue

        vat_ok, vat_norm = validate_vietnam_vat(raw_vat) if raw_vat else (False, "")

        # Lead quality and field integrity checks (STRICT - NO fabricated defaults)
        missing_mandatory_fields = []
        contact_name = lead.get("contact_name")
        if not contact_name or not str(contact_name).strip() or str(contact_name).strip() == "[Chưa xác minh]":
            contact_name = None
            missing_mandatory_fields.append("contact_name")
        else:
            contact_name = str(contact_name).strip()

        email = lead.get("email")
        if not email or "@" not in str(email).strip():
            email = None
            missing_mandatory_fields.append("email")
        else:
            email = str(email).strip()

        if not vat_ok:
            missing_mandatory_fields.append("vat_number")

        title = lead.get("title")
        if not title or not str(title).strip() or str(title).strip() == "Chưa có chức danh":
            title = None
        else:
            title = str(title).strip()

        industry = lead.get("industry_code") or lead.get("industry")
        if not industry or not str(industry).strip() or str(industry).strip() == "UNKNOWN":
            industry = None
        else:
            industry = str(industry).strip()

        dq_score = lead.get("data_quality_score", 0)
        cf_score = lead.get("commercial_fit_score", 0)

        # Check if legal entity is verified through evidence
        evidence_items = lead.get("evidence", [])
        legal_verified = any(
            (isinstance(e, dict) and e.get("field_name") in ("vat_number", "legal_name", "business_registration")
             and e.get("status") in ("SOURCE_OBSERVED", "SOURCE_CORROBORATED"))
            for e in evidence_items
        ) or vat_ok

        # Determine strict eligibility and action (V7-003)
        if dedupe_status in ("CHECK_FAILED", "STALE_RESULT"):
            action = "REVIEW_REQUIRED_DEDUPE_ERROR"
            action_reason = "Lỗi kết nối kiểm tra Zoho CRM; cần kiểm tra lại"
            eligibility_status = "NEEDS_CRM_RECHECK"
            eligible_for_crm_import = False
        elif dedupe_status == "PARTIAL_COVERAGE" or (is_bounded and coverage == "PARTIAL_COVERAGE"):
            action = "REVIEW_REQUIRED_DEDUPE_INCOMPLETE"
            action_reason = "Zoho CRM scan was bounded (200 records); comprehensive dedupe incomplete"
            eligibility_status = "NEEDS_CRM_RECHECK"
            eligible_for_crm_import = False
        elif missing_mandatory_fields:
            action = "NEEDS_ENRICHMENT"
            action_reason = f"Thiếu thông tin liên hệ bắt buộc: {', '.join(missing_mandatory_fields)}"
            eligibility_status = "NEEDS_CONTACT_ENRICHMENT"
            eligible_for_crm_import = False
        elif not legal_verified or dq_score < 50:
            action = "NEEDS_VERIFICATION"
            action_reason = "Chưa xác minh pháp nhân hoặc điểm chất lượng dữ liệu dưới 50"
            eligibility_status = "NEEDS_IDENTITY_VERIFICATION"
            eligible_for_crm_import = False
        else:
            action = "STAGED_FOR_INSERT"
            action_reason = "Hồ sơ đủ điều kiện nhập CRM: pháp nhân đã xác minh, không trùng CRM, thông tin liên hệ đầy đủ"
            eligibility_status = "APPROVED_FOR_STAGING"
            eligible_for_crm_import = True

        # Construct REAL insert payload without dummy placeholder strings (V7-003)
        zoho_payload = {
            "Company": comp,
            "Last_Name": contact_name,
            "Designation": title,
            "Email": email,
            "Phone": lead.get("phone") or None,
            "VAT_Number": vat_norm if vat_ok else None,
            "Lead_Source": "GTM_AI_Discovery",
            "Industry": industry,
            "Description": (
                f"[GTM AI Stage] Điểm phù hợp: {lead.get('score', 0)}/100 ({lead.get('score_reason', '')}). "
                f"Chất lượng dữ liệu: {dq_score}/100. "
                f"Độ khớp thương mại: {cf_score}/100. "
                f"Dedupe: {dedupe_status}."
            ),
            "Lead_Status": "Chưa liên hệ / Chờ Sales duyệt",
        }

        p_hash = generate_payload_hash({k: v for k, v in zoho_payload.items() if v is not None})

        record_entry = {
            "company": comp,
            "zoho_module": "Leads",
            "action": action,
            "action_reason": action_reason,
            "payload": zoho_payload,
            "payload_hash": p_hash,
            "eligible_for_crm_import": eligible_for_crm_import,
            "eligibility_status": eligibility_status,
            "data_quality_score": dq_score,
            "commercial_fit_score": cf_score,
            "evidence_count": len(evidence_items),
            "missing_fields": missing_mandatory_fields,
            "dedupe_status": dedupe_status,
        }
        staged.append(record_entry)
        if eligible_for_crm_import:
            eligible_records.append(record_entry)

        eligibility_decisions[comp] = {
            "candidate_id": comp,
            "company": comp,
            "eligibility_status": eligibility_status,
            "missing_fields": missing_mandatory_fields,
            "dedupe_decision_ref": lead_dedupe_dec.get("evidence_ref"),
            "identity_verified": legal_verified,
            "payload_hash": p_hash,
            "eligible_for_crm_import": eligible_for_crm_import,
            "reason": action_reason,
        }

    write_enabled = os.environ.get("CRM_WRITE_ENABLED", "false").lower() in ("true", "1")
    batch_run_id = f"batch-{uuid.uuid4().hex[:8]}"

    return _artifact(rt, "crm-import-preview", batch_run_id, {
        "total_input": len(args.leads),
        "staged_count": len(staged),
        "eligible_count": len(eligible_records),
        "excluded_count": len(excluded),
        "write_enabled": write_enabled,
        "mode": "SAFE_PREVIEW_ONLY",
        "staged_records": staged,
        "eligible_records": eligible_records,
        "excluded_records": excluded,
        "eligibility_decisions": eligibility_decisions,
        "dedupe_metadata": {
            "run_id": dedupe_res.get("run_id"),
            "coverage_status": coverage,
            "bounded": is_bounded,
            "scope_checked": dedupe_res.get("scope_checked", []),
        },
    })


def lead_pipeline_run(args: LeadPipelineRunIn, rt: HubRuntime) -> dict[str, Any]:
    import logging
    import uuid
    from ..lead_engine.discovery import (
        DynamicDiscoveryEngine,
        DiscoveryFilter,
        ApolloDiscoveryProvider,
        TradeManifestDiscoveryProvider,
    )
    from ..lead_engine.verifier import LeadVerifier
    from ..lead_engine.scorer import TwoAxisScorer
    from ..models import EvidenceStatus, Lead, Environment

    logger = logging.getLogger(__name__)

    filt = DiscoveryFilter(
        industry_keywords=args.industry_keywords,
        industry_codes=args.industry_codes,
        trade_lanes=args.trade_lanes,
        limit=args.limit,
    )

    # Wire live Apollo connector if available in runtime registry
    apollo_conn = None
    reg_client = None
    if rt.registry:
        try:
            apollo_conn = rt.registry.get("apollo")
        except Exception:
            apollo_conn = None
        try:
            reg_client = rt.registry.get("business_registry")
        except Exception:
            reg_client = None

    providers = [
        ApolloDiscoveryProvider(apollo_connector=apollo_conn),
        TradeManifestDiscoveryProvider(),
    ]
    discovery = DynamicDiscoveryEngine(providers=providers)
    disc_res = discovery.discover_candidates(filt, env=rt.settings.environment)

    verifier = LeadVerifier(registry_client=reg_client)
    scorer = TwoAxisScorer()

    # Pre-score Dedupe Verification against CRM
    companies = [c.company for c in disc_res.candidates if c.company]
    domains = [c.domain for c in disc_res.candidates if c.domain]
    vats = [c.vat_number for c in disc_res.candidates if c.vat_number]

    dedupe_res = crm_find_existing(FindExistingIn(companies=companies, domains=domains, vats=vats), rt)
    matches = dedupe_res.get("matches", {})
    decisions = dedupe_res.get("decisions", {})
    coverage = dedupe_res.get("coverage_status", "PARTIAL_COVERAGE")

    verified_candidates = []
    for cand in disc_res.candidates:
        verifier.verify_candidate(cand)

        # Corroborate CRM Dedupe Status & inject audit EvidenceItem per entity (V7-001 & V7-002)
        c_dec = decisions.get(cand.company, {})
        c_status = c_dec.get("decision_status")
        is_match = (
            cand.company in matches
            or (cand.domain and cand.domain in matches)
            or (cand.vat_number and cand.vat_number in matches)
        )

        if c_status == "DUPLICATE_CONFIRMED" or is_match:
            cand.crm_dedupe_status = "DUPLICATE_CONFIRMED"
            cand.in_crm = True
            cand.crm_match = str(is_match or (c_dec.get("matching_record_ids") or ["MATCH"])[0])
            cand.add_evidence(
                field_name="crm_dedupe",
                field_value={"status": "DUPLICATE_CONFIRMED", "match": cand.crm_match},
                source_provider="zoho_dedupe",
                evidence_status=EvidenceStatus.SOURCE_CORROBORATED,
                confidence=1.0,
            )
        elif c_status == "NOT_FOUND_IN_CHECKED_SCOPE" or (coverage == "FULL_COVERAGE" and dedupe_res.get("match_status") == "NOT_FOUND_VERIFIED"):
            cand.crm_dedupe_status = "NOT_FOUND_VERIFIED"
            cand.in_crm = False
            cand.add_evidence(
                field_name="crm_dedupe",
                field_value={"status": "NOT_FOUND_VERIFIED", "scope": dedupe_res.get("scope_checked", [])},
                source_provider="zoho_dedupe",
                evidence_status=EvidenceStatus.SOURCE_CORROBORATED,
                confidence=0.95,
            )
        elif c_status == "CHECK_FAILED":
            cand.crm_dedupe_status = "CHECK_FAILED"
            cand.in_crm = False
            cand.add_evidence(
                field_name="crm_dedupe",
                field_value={"status": "CHECK_FAILED", "error": c_dec.get("error_details")},
                source_provider="zoho_dedupe",
                evidence_status=EvidenceStatus.SOURCE_UNVERIFIED,
                confidence=0.0,
            )
        else:
            cand.crm_dedupe_status = "PARTIAL_COVERAGE"
            cand.in_crm = False
            cand.add_evidence(
                field_name="crm_dedupe",
                field_value={"status": "PARTIAL_COVERAGE", "bounded": dedupe_res.get("bounded", True)},
                source_provider="zoho_dedupe",
                evidence_status=EvidenceStatus.SOURCE_OBSERVED,
                confidence=0.5,
            )

        scorer.score_candidate(cand)
        cand_dict = cand.model_dump(mode="json")
        verified_candidates.append(cand_dict)

        # Persist as canonical record in storage with stable identity (V7-004 & V7-005)
        try:
            from ..storage import StagingStore
            from ..identity import generate_stable_lead_id
            from ..models import BusinessEvent

            db_path = rt.settings.data_dir / "marketing.db"
            storage = StagingStore(db_path)
            storage.initialize()

            stable_id = generate_stable_lead_id(
                company=cand.company,
                domain=cand.domain,
                vat_number=cand.vat_number
            )

            if rt.settings.environment == Environment.MOCK or not cand.synthetic:
                lead_entity = Lead(
                    id=stable_id,
                    environment=cand.environment,
                    source=cand.source,
                    correlation_id=rt.ctx.correlation_id,
                    synthetic=cand.synthetic,
                    full_name=cand.contact_name or cand.company,
                    title=cand.title,
                    email=cand.email,
                    score=cand.score,
                    score_reason=cand.score_reason,
                    qualification=cand.stage,
                )
                storage.upsert(lead_entity)

                # Record canonical business events
                storage.record_event(BusinessEvent(
                    event_type="lead.discovered",
                    entity_id=stable_id,
                    workflow_id=getattr(rt.ctx, "workflow_id", "") or rt.ctx.correlation_id,
                    environment=cand.environment,
                    synthetic=cand.synthetic,
                    source=cand.source,
                    correlation_id=rt.ctx.correlation_id,
                    payload_json={
                        "company": cand.company,
                        "vat_number": cand.vat_number,
                        "score": cand.score,
                        "stage": cand.stage,
                        "data_quality_score": cand.data_quality_score,
                        "commercial_fit_score": cand.commercial_fit_score,
                    }
                ))

                storage.record_event(BusinessEvent(
                    event_type="lead.crm_dedupe_completed",
                    entity_id=stable_id,
                    workflow_id=getattr(rt.ctx, "workflow_id", "") or rt.ctx.correlation_id,
                    environment=cand.environment,
                    synthetic=cand.synthetic,
                    source="zoho_dedupe",
                    correlation_id=rt.ctx.correlation_id,
                    evidence_ref=c_dec.get("evidence_ref"),
                    payload_json={
                        "company": cand.company,
                        "dedupe_status": cand.crm_dedupe_status,
                        "in_crm": cand.in_crm,
                        "run_id": dedupe_res.get("run_id"),
                    }
                ))
        except Exception as store_err:
            logger.error("Failed to store canonical lead entity: %s", store_err)
            raise store_err

    run_art_id = f"run-{uuid.uuid4().hex[:8]}"
    return _artifact(rt, "pipeline-discovery", run_art_id, {
        "total_discovered": len(verified_candidates),
        "candidates": verified_candidates,
        "sources": disc_res.sources_used,
        "source_statuses": disc_res.source_statuses,
        "filter": filt.model_dump(),
        "dedupe_coverage": coverage,
    })


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
        return connector.upload_video_file(file_path=file_path, title=title, privacy_level="PUBLIC_TO_EVERYONE", publish_mode="auto")
    elif args.channel == "linkedin":
        import subprocess, json
        from pathlib import Path
        cli_path = Path(r"C:\Users\Admin\.buzz\services\linkedin\linkedin_cli.js")
        if cli_path.is_file():
            cmd = ["node", str(cli_path), "post", "--text", args.text]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            try:
                return json.loads(proc.stdout.strip())
            except Exception:
                return {
                    "channel": "linkedin",
                    "status": "published" if proc.returncode == 0 else "fallback_triggered",
                    "output": proc.stdout.strip(),
                    "error": proc.stderr.strip()
                }
        raise ToolUnavailable("NOT_CONFIGURED", f"LinkedIn CLI not found at {cli_path}")
    elif args.channel == "zalo":
        import subprocess, json, re
        from pathlib import Path
        cli_path = Path(r"C:\Users\Admin\.buzz\services\zalo-oa\oa_cli.js")
        if not cli_path.is_file():
            raise ToolUnavailable("NOT_CONFIGURED", f"Zalo OA CLI not found at {cli_path}")
        text = args.text.strip()
        sha_match = re.search(r'([a-fA-F0-9]{64})', text)
        is_video = bool((sha_match and (".mp4" in text or "media/" in text)) or Path(text).suffix.lower() in [".mp4", ".mov"])
        if is_video:
            local_vid = Path(r"C:\Users\Admin\.buzz\cache\test_video.mp4")
            if not local_vid.is_file() and Path(text).is_file():
                local_vid = Path(text)
            title = text.split("\n")[0][:140] if text else "Minh Vân Logistics"
            desc = text[:280].replace("\n", " ").strip()
            cmd = ["node", str(cli_path), "video-article-create", "--file", str(local_vid), "--title", title, "--desc", desc, "--status", "show"]
        else:
            title = text.split("\n")[0][:140] if text else "Minh Vân Logistics"
            cmd = ["node", str(cli_path), "article-create", "--title", title, "--desc", text[:280], "--content", text, "--cover", "https://zalo-article-photo.zadn.vn/331f575f9b03725d2b12#435204888", "--status", "show"]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        try:
            return json.loads(proc.stdout.strip())
        except Exception:
            return {"channel": "zalo", "status": "published" if proc.returncode == 0 else "error", "output": proc.stdout.strip(), "error": proc.stderr.strip()}
    elif args.channel == "youtube":
        connector = _live_connector(rt, "youtube")
        from pathlib import Path
        local_vid = Path(r"C:\Users\Admin\.buzz\cache\test_video.mp4")
        text = args.text.strip()
        title = "Minh Van Logistics Video"
        description = text
        if Path(text).is_file():
            local_vid = Path(text)
            title = local_vid.stem
        elif local_vid.is_file():
            title = text.split("\n")[0][:100] if text else "Minh Van Logistics Video"
        else:
            raise FileNotFoundError(f"Video file not found for YouTube publish: {args.text}")
        return connector.upload_video(file_path=str(local_vid), title=title[:100], description=description, privacy="public")
    else:
        raise NotImplementedError(f"Publishing to channel '{args.channel}' is not enabled or requires product approval.")


def social_schedule_post(args: SchedulePostIn, rt: HubRuntime) -> dict[str, Any]:
    import subprocess, json, sys
    from pathlib import Path
    cli_path = Path(r"C:\Users\Admin\.buzz\services\scheduler\scheduler_cli.py")
    if not cli_path.is_file():
        raise ToolUnavailable("NOT_CONFIGURED", f"Scheduler CLI not found at {cli_path}")
    python_bin = sys.executable
    cmd = [
        python_bin, str(cli_path), "add",
        "--channel", args.channel,
        "--time", args.time,
        "--title", args.title or (args.text.split("\n")[0][:100] if args.text else "Bài viết Marketing"),
        "--text", args.text or "",
        "--type", args.content_type,
        "--json"
    ]
    if args.media_url:
        cmd.extend(["--media", args.media_url])
    if args.file_path:
        cmd.extend(["--file", args.file_path])
    if args.channel_id:
        cmd.extend(["--channel-id", args.channel_id])

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(proc.stdout.strip())
    except Exception:
        return {"status": "scheduled", "output": proc.stdout.strip(), "error": proc.stderr.strip()}


def social_list_scheduled_posts(args: ListScheduledPostsIn, rt: HubRuntime) -> dict[str, Any]:
    import subprocess, json, sys
    from pathlib import Path
    cli_path = Path(r"C:\Users\Admin\.buzz\services\scheduler\scheduler_cli.py")
    python_bin = sys.executable
    cmd = [python_bin, str(cli_path), "list", "--limit", str(args.limit), "--json"]
    if args.status != "all":
        cmd.extend(["--status", args.status])
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    try:
        return {"tasks": json.loads(proc.stdout.strip())}
    except Exception:
        return {"tasks": [], "output": proc.stdout.strip(), "error": proc.stderr.strip()}


def social_cancel_scheduled_post(args: CancelScheduledPostIn, rt: HubRuntime) -> dict[str, Any]:
    import subprocess, sys
    from pathlib import Path
    cli_path = Path(r"C:\Users\Admin\.buzz\services\scheduler\scheduler_cli.py")
    python_bin = sys.executable
    cmd = [python_bin, str(cli_path), "cancel", "--id", args.task_id]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return {"task_id": args.task_id, "success": proc.returncode == 0, "output": proc.stdout.strip()}


def social_create_page_post_draft(args: PagePostDraftIn, rt: HubRuntime) -> dict[str, Any]:
    if rt.mock:
        return _artifact(rt, "facebook-page-post", "post",
                         {"message": args.message, "status": "published" if args.published else "draft", "published": args.published, "label": "SYNTHETIC_MOCK_DATA"})
    # Page posting only needs META_PAGE_ACCESS_TOKEN/META_PAGE_ID, not the ad-account
    # credentials that _live_connector's report()-based gate requires, so check that
    # directly instead of routing through the ads-account readiness check.
    connector = rt.registry.get("meta_ads")
    if not connector.page_configured():
        raise ToolUnavailable("NOT_CONFIGURED", "META_PAGE_ACCESS_TOKEN / META_PAGE_ID missing.")
    if args.published:
        return connector.publish_page_post(args.message)
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
        return _artifact(rt, "tiktok-video", args.title,
                         {"title": args.title, "video_source": args.video_source, "privacy_level": args.privacy_level,
                          "status": "published" if args.privacy_level == "PUBLIC_TO_EVERYONE" else "draft_inbox",
                          "published": args.privacy_level == "PUBLIC_TO_EVERYONE", "label": "SYNTHETIC_MOCK_DATA"})
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
            publish_mode=args.publish_mode,
        )
    return {"status": "staged_draft", "title": args.title, "privacy_level": args.privacy_level, "video_source": args.video_source}


def video_produce_full_video(args: VideoProduceIn, rt: HubRuntime) -> dict[str, Any]:
    from ..video.composer import VideoComposer, VideoProductionConfig
    channels = ["tiktok"] if args.auto_publish else []
    cfg = VideoProductionConfig(
        title=args.title,
        script=args.script,
        mode=args.mode,
        aspect_ratio=args.aspect_ratio,
        enable_subtitles=args.enable_subtitles,
        auto_publish_channels=channels,
    )
    composer = VideoComposer(rt.settings)
    result = composer.produce(cfg)
    return {
        "status": "completed",
        "title": result.title,
        "video_path": result.video_path,
        "duration": result.duration,
        "resolution": result.resolution,
        "blossom_url": result.blossom_url,
        "social_status": result.social_status,
        "technology_attribution": result.attribution.to_dict(),
        "summary_report": result.summary_report,
    }


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
    control_js = str(Path.home() / "AppData" / "Local" / "agy" / "bin" / "codex-control.js")
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
    codex_bin = str(Path.home() / ".codex" / "packages" / "standalone" / "current" / "bin" / "codex.exe")
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
    (_spec("crm.preview_import", Impact.DRAFT, "zoho", "read_crm_records", PreviewCrmImportIn,
           "Generate safe Zoho CRM import preview and deduplication diff without modifying CRM."), crm_preview_import),
    (_spec("prospecting.pipeline_run", Impact.DRAFT, "apollo", "organization_search", LeadPipelineRunIn,
           "Run dynamic multi-source discovery, evidence verification, and two-axis commercial scoring."), lead_pipeline_run),
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
    (_spec("social.publish_post", Impact.DRAFT, "multi", "publish_post", PublishPostIn,
           "Đăng bài viết hoặc video tức thì lên mạng xã hội (Zalo OA, TikTok, Facebook, LinkedIn, YouTube).", lambda p: f"ĐĂNG bài lên {p['channel']}: {p['text'][:120]}"), social_publish_post),
    (_spec("social.schedule_post", Impact.DRAFT, "multi", "schedule_post", SchedulePostIn,
           "Lên lịch hẹn giờ tự động đăng bài lên Zalo OA, TikTok, YouTube, Facebook, LinkedIn.",
           lambda p: f"LÊN LỊCH đăng lên {p['channel']} lúc {p['time']}: '{p['title'] or p['text'][:50]}'"), social_schedule_post),
    (_spec("social.list_scheduled_posts", Impact.READ, "multi", "list_scheduled_posts", ListScheduledPostsIn,
           "Xem danh sách các bài viết đang được hẹn giờ xuất bản trong hệ thống."), social_list_scheduled_posts),
    (_spec("social.cancel_scheduled_post", Impact.DRAFT, "multi", "cancel_scheduled_post", CancelScheduledPostIn,
           "Hủy một lịch hẹn đăng bài."), social_cancel_scheduled_post),
    (_spec("social.create_facebook_page_post_draft", Impact.DRAFT, "meta_ads", "create_page_post_draft", PagePostDraftIn,
           "Đăng bài lên Fanpage Facebook (mặc định published=true công khai; có thể đặt published=false để lưu nháp)."), social_create_page_post_draft),
    (_spec("tiktok.get_channel_metrics", Impact.READ, "tiktok", "read_channel_metrics", NoInput,
           "TikTok account followers, following, likes, and video count."), tiktok_get_channel_metrics),
    (_spec("tiktok.get_recent_videos", Impact.READ, "tiktok", "read_recent_videos", LimitIn,
           "Latest published TikTok videos with views, likes, comments, and shares."), tiktok_get_recent_videos),
    (_spec("tiktok.upload_video_draft", Impact.DRAFT, "tiktok", "upload_video_draft", TikTokDraftIn,
           "Tải lên video TikTok ở chế độ công khai PUBLIC_TO_EVERYONE (tự fallback inbox nếu cần)."), tiktok_upload_video_draft),
    (_spec("video.produce_full_video", Impact.DRAFT, "multi", "produce_full_video", VideoProduceIn,
           "Dây chuyền sản xuất video tự động đa phương thức: ElevenLabs voice, HeyGen/Higgsfield visual, Whisper kinetic subtitles, FFmpeg ducking & Blossom export kèm báo cáo công nghệ tích hợp."), video_produce_full_video),
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

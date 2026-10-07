"""Workflow definitions. Steps are deterministic; language work goes through the runtime."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..models import LeadCandidate
from .engine import StepContext, StepOutcome, WorkflowDefinition, WorkflowStep

_BLOCKING = {"NEEDS_AUTH", "NEEDS_MFA", "NEEDS_API_ACCESS", "NOT_CONFIGURED", "NOT_IMPLEMENTED", "DENIED", "ERROR", "INVALID_INPUT"}


def _tool_outcome(result, output_key: str | None = None) -> StepOutcome | None:
    """Translate a non-success ToolResult into a step outcome; None means success."""
    if result.succeeded:
        return None
    if result.state == "APPROVAL_REQUIRED":
        return StepOutcome(status="wait_approval", approval_id=result.approval["approval_id"], detail=result.approval["code"])
    return StepOutcome(status="blocked", detail=f"{result.tool} → {result.state}: {result.detail}"[:500],
                       output={"tool": result.tool, "state": result.state})


# ---------------------------------------------------------------- scoring (code, not LLM)
_SENIOR = ("director", "giám đốc", "head", "trưởng", "chief", "ceo", "coo", "founder")
_MID = ("manager", "quản lý", "lead")
_FIT = ("logistics", "forwarding", "xuất nhập khẩu", "xuat nhap khau", "supply chain", "chuỗi cung ứng",
        "import", "export", "vận tải", "thương mại", "nhà máy", "factory", "trading")


def score_candidate(candidate: dict[str, Any]) -> tuple[int, dict[str, int], str]:
    title = (candidate.get("title") or "").lower()
    text = " ".join(str(candidate.get(k) or "") for k in ("company", "title", "score_reason")).lower()
    breakdown = {
        "seniority": 30 if any(k in title for k in _SENIOR) else 20 if any(k in title for k in _MID) else 5,
        "industry_fit": 30 if any(k in text for k in _FIT) else 0,
        "has_contact": 15 if candidate.get("contact_name") else 0,
        "has_domain": 10 if candidate.get("domain") else 0,
        "not_in_crm": 15 if not candidate.get("in_crm") else 0,
    }
    total = min(sum(breakdown.values()), 100)
    reason = ", ".join(f"{k}+{v}" for k, v in breakdown.items() if v)
    return total, breakdown, reason


# ---------------------------------------------------------------- prospect → draft (North Star)
def step_search(ctx: StepContext) -> StepOutcome:
    p = ctx.params
    result = ctx.tool("prospecting.search_companies", {"industry": p.get("industry", "logistics"),
                                                       "location": p.get("location", "Vietnam"),
                                                       "keywords": p.get("keywords", []), "limit": p.get("count", 10)})
    return _tool_outcome(result) or StepOutcome(status="done", output={"candidates": result.data, "source_state": result.state})


def step_dedupe(ctx: StepContext) -> StepOutcome:
    candidates = ctx.outputs["search"]["candidates"]
    result = ctx.tool("crm.find_existing", {"companies": [c["company"] for c in candidates],
                                            "domains": [c["domain"] for c in candidates if c.get("domain")]})
    blocked = _tool_outcome(result)
    if blocked:
        return blocked
    matches = result.data["matches"]
    for c in candidates:
        hit = matches.get(c["company"]) or (matches.get(c["domain"]) if c.get("domain") else None)
        c["in_crm"], c["crm_match"] = bool(hit), hit
    return StepOutcome(status="done", output={"candidates": candidates, "excluded": [c["company"] for c in candidates if c["in_crm"]],
                                              "accounts_scanned": result.data["accounts_scanned"]})


def step_score(ctx: StepContext) -> StepOutcome:
    ranked = []
    for c in ctx.outputs["dedupe"]["candidates"]:
        if c.get("in_crm"):
            continue
        total, breakdown, reason = score_candidate(c)
        ranked.append(LeadCandidate(**{**c, "score": total, "score_breakdown": breakdown, "score_reason": reason}).model_dump(mode="json"))
    ranked.sort(key=lambda c: (-c["score"], c["company"]))
    top = ranked[: int(ctx.params.get("top_n", 3))]
    if not top:
        return StepOutcome(status="blocked", detail="No new candidates after CRM dedupe.")
    return StepOutcome(status="done", output={"ranked": ranked, "top": top})


class _Draft(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=8000)


def step_draft_emails(ctx: StepContext) -> StepOutcome:
    drafts = []
    for lead in ctx.outputs["score"]["top"]:
        facts = {k: lead.get(k) for k in ("company", "contact_name", "title", "domain", "score_reason")}
        prompt = (
            "SCHEMA:EmailDraft. Viết email tiếp cận lần đầu bằng tiếng Việt, lịch sự, ngắn (<150 từ), "
            "cho dịch vụ logistics/forwarding của Công ty CP Vận tải Quốc tế Minh Vân. "
            "Chỉ dùng các dữ kiện sau, không bịa số liệu hay cam kết giá:\n"
            + json.dumps(facts, ensure_ascii=False)
            + '\nTrả về JSON {"subject": "...", "body": "..."}.'
        )
        draft = None
        for attempt in range(2):  # LLM output is not guaranteed; retry once with a stricter reminder
            answer = ctx.ask(prompt if attempt == 0 else prompt + "\nCHỈ in ra đúng một object JSON, không kèm chữ nào khác.",
                             specialist="04_content", expect_json=True)
            if not answer.ok:
                return StepOutcome(status="blocked", detail=f"runtime {answer.runtime} → {answer.error_code}")
            try:
                draft = _Draft.model_validate(answer.structured or {})
                break
            except ValidationError:
                continue
        if draft is None:
            return StepOutcome(status="failed", detail=f"runtime {answer.runtime} returned no valid EmailDraft JSON")
        drafts.append({"lead_company": lead["company"], "to_name": lead.get("contact_name"),
                       "to_email": lead.get("email"), **draft.model_dump()})
    return StepOutcome(status="done", output={"drafts": drafts})


def step_approve_drafts(ctx: StepContext) -> StepOutcome:
    drafts = ctx.outputs["draft_emails"]["drafts"]
    summary = "Tạo Outlook draft (không gửi) cho: " + "; ".join(f"{d['lead_company']} — '{d['subject']}'" for d in drafts)
    return ctx.gate("workflow.create_outlook_drafts", drafts, summary)


def step_create_drafts(ctx: StepContext) -> StepOutcome:
    created = []
    for draft in ctx.outputs["draft_emails"]["drafts"]:
        key = f"{ctx.workflow['workflow_id']}:email-draft:{draft['lead_company']}"
        result = ctx.tool("email.create_draft", draft, idempotency_key=key, specialist="06_sales_copilot")
        blocked = _tool_outcome(result)
        if blocked:
            return blocked
        created.append({"company": draft["lead_company"], "state": result.state, "artifact": (result.data or {}).get("artifact")})
    return StepOutcome(status="done", output={"created": created})


def step_propose_tasks(ctx: StepContext) -> StepOutcome:
    proposals = []
    for lead in ctx.outputs["score"]["top"]:
        key = f"{ctx.workflow['workflow_id']}:task:{lead['company']}"
        result = ctx.tool("crm.propose_task", {"subject": f"Follow-up email tiếp cận {lead['company']}",
                                               "related_company": lead["company"], "due_in_days": 3,
                                               "reason": f"Lead mới, điểm {lead['score']}/100 ({lead['score_reason']})"},
                          idempotency_key=key, specialist="06_sales_copilot")
        blocked = _tool_outcome(result)
        if blocked:
            return blocked
        proposals.append({"company": lead["company"], "artifact": (result.data or {}).get("artifact")})
    return StepOutcome(status="done", output={"proposals": proposals})


def finalize_prospect(wf: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    top = out.get("score", {}).get("top", [])
    return {
        "environment": wf["environment"],
        "found": len(out.get("search", {}).get("candidates", [])),
        "excluded_in_crm": out.get("dedupe", {}).get("excluded", []),
        "top": [{"company": c["company"], "score": c["score"], "reason": c["score_reason"]} for c in top],
        "drafts": out.get("create_drafts", {}).get("created", []),
        "task_proposals": out.get("propose_tasks", {}).get("proposals", []),
        "emails_sent": 0,
        "crm_writes": 0,
    }


PROSPECT_TO_DRAFT = WorkflowDefinition(
    workflow_type="prospect_to_draft",
    description="Find companies → CRM dedupe → score → draft emails → owner approval → Outlook drafts → Sales task proposals.",
    steps=[
        WorkflowStep("search", "03_account_intelligence", step_search),
        WorkflowStep("dedupe", "03_account_intelligence", step_dedupe),
        WorkflowStep("score", "03_account_intelligence", step_score),
        WorkflowStep("draft_emails", "04_content", step_draft_emails),
        WorkflowStep("approve_drafts", "06_sales_copilot", step_approve_drafts),
        WorkflowStep("create_drafts", "06_sales_copilot", step_create_drafts),
        WorkflowStep("propose_tasks", "06_sales_copilot", step_propose_tasks),
    ],
    finalize=finalize_prospect,
)


# ---------------------------------------------------------------- single approved tool call
def step_tool_call(ctx: StepContext) -> StepOutcome:
    p = ctx.params
    result = ctx.tool(p["tool"], p.get("args", {}), use_approval=True, specialist=p.get("specialist"),
                      idempotency_key=f"{ctx.workflow['workflow_id']}:call")
    return _tool_outcome(result) or StepOutcome(status="done", output={"state": result.state, "data": result.data})


TOOL_APPROVAL = WorkflowDefinition(
    workflow_type="tool_approval",
    description="One tool call that needs a verified human approval before it runs.",
    steps=[WorkflowStep("call", "00_orchestrator", step_tool_call)],
)


# ---------------------------------------------------------------- video production pipeline
def step_video_plan(ctx: StepContext) -> StepOutcome:
    p = ctx.params
    title = p.get("title", "Video Minh Van Logistics")
    script = p.get("script", "")
    mode = p.get("mode", "hybrid")
    ratio = p.get("aspect_ratio", "9:16")

    if not script:
        # Prompt Content Specialist for high-hook 30s-45s script
        prompt = (
            f"SCHEMA:VideoScript. Viết kịch bản video ngắn (30-45 giây, dưới 100 từ) cho chủ đề: '{title}'.\n"
            "Cấu trúc bắt buộc: 3 giây đầu câu hook giữ chân + 25 giây thân bài chia sẻ giá trị thực tế logistics + 5 giây kêu gọi hành động.\n"
            "Chỉ in ra nội dung lời đọc bằng tiếng Việt, tự nhiên và chuyên nghiệp."
        )
        ans = ctx.ask(prompt, specialist="04_content")
        script = ans.text if ans.ok else "Chào mừng bạn đến với giải pháp logistics và vận chuyển quốc tế của Minh Vân."

    return StepOutcome(status="done", output={"title": title, "script": script, "mode": mode, "aspect_ratio": ratio})


def step_video_compose(ctx: StepContext) -> StepOutcome:
    plan = ctx.outputs["plan"]
    p = ctx.params
    auto_pub = p.get("auto_publish", False)

    result = ctx.tool(
        "video.produce_full_video",
        {
            "title": plan["title"],
            "script": plan["script"],
            "mode": plan["mode"],
            "aspect_ratio": plan["aspect_ratio"],
            "enable_subtitles": p.get("enable_subtitles", True),
            "auto_publish": auto_pub,
        },
        idempotency_key=f"{ctx.workflow['workflow_id']}:compose",
        specialist="04_content",
    )
    blocked = _tool_outcome(result)
    if blocked:
        return blocked

    return StepOutcome(status="done", output=result.data)


def finalize_video(wf: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    comp = out.get("compose", {})
    return {
        "workflow_id": wf.get("workflow_id"),
        "title": comp.get("title"),
        "duration": comp.get("duration"),
        "video_path": comp.get("video_path"),
        "blossom_url": comp.get("blossom_url"),
        "technology_attribution": comp.get("technology_attribution", {}),
        "social_status": comp.get("social_status", {}),
        "summary_report": comp.get("summary_report", ""),
    }


VIDEO_PRODUCTION = WorkflowDefinition(
    workflow_type="video_production",
    description="End-to-End AI Video Pipeline: Script Hook 3s → ElevenLabs/HeyGen Voice → Visual B-roll → Whisper Kinetic Subtitles → FFmpeg Ducking → Blossom Export → Multi-platform Attribution.",
    steps=[
        WorkflowStep("plan", "04_content", step_video_plan),
        WorkflowStep("compose", "04_content", step_video_compose),
    ],
    finalize=finalize_video,
)

DEFINITIONS: dict[str, WorkflowDefinition] = {
    d.workflow_type: d for d in (PROSPECT_TO_DRAFT, TOOL_APPROVAL, VIDEO_PRODUCTION)
}

"""The eight logical specialists.

A specialist is data, not a process: instructions (the Hermes skill file that
already exists), the tool namespaces it may use, and the highest impact level
it may even request. Any runtime can play any specialist.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from .config import PROJECT_ROOT
from .constants import Impact

_SKILLS_DIR = PROJECT_ROOT / "hermes" / "skills"

IMPACT_ORDER = {Impact.READ: 0, Impact.DRAFT: 1, Impact.WRITE_LOW_RISK: 2, Impact.HIGH_IMPACT: 3}


class Specialist(BaseModel):
    id: str
    name: str
    purpose: str
    skill: str
    namespaces: tuple[str, ...]
    max_impact: Impact
    output_schema: str

    def instructions(self) -> str:
        return _skill_body(self.skill)

    def allows(self, namespace: str, impact: Impact) -> bool:
        return namespace in self.namespaces and IMPACT_ORDER[impact] <= IMPACT_ORDER[self.max_impact]


ORCHESTRATOR = Specialist(
    id="00_orchestrator",
    name="Điều phối",
    purpose="Route requests, report system state, run workflows.",
    skill="marketing-orchestrator",
    namespaces=("system", "workflow", "crm", "prospecting", "website", "social", "tiktok", "analytics", "ads", "email", "files", "codex", "meta_ai"),
    max_impact=Impact.HIGH_IMPACT,
    output_schema="RouteDecision",
)

SPECIALISTS: dict[str, Specialist] = {
    s.id: s
    for s in (
        Specialist(id="01_strategy", name="Chiến lược", purpose="ICP, positioning, objectives, priorities.",
                   skill="marketing-strategy", namespaces=("crm", "analytics", "website", "social", "tiktok", "ads", "knowledge", "files", "codex", "meta_ai"),
                   max_impact=Impact.DRAFT, output_schema="StrategyBrief"),
        Specialist(id="02_market_intelligence", name="Tình báo thị trường", purpose="Competitors and market signals, source-backed.",
                   skill="marketing-market-intelligence", namespaces=("prospecting", "website", "seo", "knowledge", "files", "codex"),
                   max_impact=Impact.READ, output_schema="MarketFindings"),
        Specialist(id="03_account_intelligence", name="Tình báo khách hàng", purpose="Lead/account search, dedupe, scoring.",
                   skill="marketing-account-intelligence", namespaces=("crm", "prospecting", "knowledge", "files", "codex"),
                   max_impact=Impact.DRAFT, output_schema="LeadCandidate[]"),
        Specialist(id="04_content", name="Nội dung", purpose="Channel copy, briefs, and authorized social publishing.",
                   skill="marketing-content", namespaces=("content", "website", "social", "tiktok", "files", "knowledge", "codex", "meta_ai"),
                   max_impact=Impact.HIGH_IMPACT, output_schema="ContentAsset"),
        Specialist(id="05_seo_geo", name="SEO/GEO", purpose="Search and AI-answer visibility.",
                   skill="marketing-seo-geo", namespaces=("seo", "website", "analytics", "knowledge", "files", "codex"),
                   max_impact=Impact.DRAFT, output_schema="SeoRecommendations"),
        Specialist(id="06_sales_copilot", name="Trợ lý bán hàng", purpose="Call prep, follow-ups, email drafts, task proposals.",
                   skill="marketing-sales-copilot", namespaces=("crm", "email", "calendar", "files", "knowledge", "codex"),
                   max_impact=Impact.WRITE_LOW_RISK, output_schema="SalesBrief"),
        Specialist(id="07_campaign", name="Chiến dịch", purpose="Multi-channel campaign plans and coordinated publishing.",
                   skill="marketing-campaign", namespaces=("ads", "social", "tiktok", "content", "analytics", "knowledge", "files", "codex", "meta_ai"),
                   max_impact=Impact.HIGH_IMPACT, output_schema="CampaignPlan"),
        Specialist(id="08_kpi_learning", name="KPI & học hỏi", purpose="Metrics, attribution, FACT/INFERENCE/HYPOTHESIS.",
                   skill="marketing-kpi-learning", namespaces=("analytics", "crm", "ads", "social", "tiktok", "website", "files", "codex"),
                   max_impact=Impact.READ, output_schema="MetricSnapshot"),
    )
}


def get_specialist(specialist_id: str) -> Specialist:
    if specialist_id == ORCHESTRATOR.id:
        return ORCHESTRATOR
    try:
        return SPECIALISTS[specialist_id]
    except KeyError:
        raise KeyError(f"Unknown specialist: {specialist_id}") from None


@lru_cache(maxsize=None)
def _skill_body(skill: str) -> str:
    path = _SKILLS_DIR / skill / "SKILL.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


def skills_dir() -> Path:
    return _SKILLS_DIR

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .constants import Environment


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseEntity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    external_id: str | None = None
    source: str
    environment: Environment = Environment.MOCK
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: str = "new"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    owner: str | None = None
    correlation_id: str
    synthetic: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Company(BaseEntity):
    name: str
    domain: str | None = None
    industry: str | None = None
    employee_range: str | None = None
    country: str | None = None


class Account(Company):
    account_tier: str | None = None
    relationship_status: str | None = None


class Contact(BaseEntity):
    full_name: str
    title: str | None = None
    email: str | None = None
    company_id: str | None = None


class Lead(Contact):
    score: int = Field(default=0, ge=0, le=100)
    score_reason: str = ""
    qualification: str = "unqualified"


class Opportunity(BaseEntity):
    account_id: str
    name: str
    stage: str
    amount: float | None = None
    currency: str = "VND"


class Deal(Opportunity):
    expected_close_date: datetime | None = None


class Task(BaseEntity):
    title: str
    due_at: datetime | None = None
    related_entity_id: str | None = None


class Campaign(BaseEntity):
    name: str
    objective: str
    channels: list[str] = Field(default_factory=list)
    budget_proposal: float | None = None
    currency: str = "VND"
    execution_state: Literal["draft", "approval_required", "scheduled", "active"] = "draft"


class ContentAsset(BaseEntity):
    title: str
    channel: str
    body: str
    publication_state: Literal["draft", "approval_required", "published"] = "draft"


class ChannelPost(ContentAsset):
    channel_post_id: str | None = None


class AdCampaign(Campaign):
    platform: str
    live_campaign_id: str | None = None


class Metric(BaseEntity):
    name: str
    value: float
    unit: str
    period_start: datetime | None = None
    period_end: datetime | None = None


class Activity(BaseEntity):
    activity_type: str
    summary: str
    related_entity_id: str | None = None


class SourceReference(BaseEntity):
    url: str
    title: str | None = None
    accessed_at: datetime = Field(default_factory=utc_now)


CanonicalEntity = (
    Lead
    | Contact
    | Account
    | Company
    | Opportunity
    | Deal
    | Task
    | Campaign
    | ContentAsset
    | ChannelPost
    | AdCampaign
    | Metric
    | Activity
    | SourceReference
)


class LeadCandidate(BaseModel):
    """Prospect after dedupe/scoring; crosses the Account Intelligence → Sales Copilot boundary."""

    company: str
    domain: str | None = None
    contact_name: str | None = None
    title: str | None = None
    email: str | None = None
    source: str
    environment: Environment
    synthetic: bool = False
    in_crm: bool = False
    crm_match: str | None = None
    score: int = Field(default=0, ge=0, le=100)
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    score_reason: str = ""
    source_reference: str | None = None


class EmailDraft(BaseModel):
    to_name: str | None = None
    to_email: str | None = None
    subject: str
    body: str
    lead_company: str
    environment: Environment
    status: Literal["local_draft", "provider_draft"] = "local_draft"
    provider_id: str | None = None


class TaskProposal(BaseModel):
    """A proposed Sales task. Not written to Zoho; Sales decides."""

    subject: str
    related_company: str
    due_in_days: int = 3
    owner_hint: str | None = None
    reason: str
    environment: Environment


class MetricSnapshot(BaseModel):
    name: str
    value: float | int | None
    unit: str = ""
    source: str
    kind: Literal["FACT", "INFERENCE", "HYPOTHESIS", "RECOMMENDATION"] = "FACT"
    as_of: datetime = Field(default_factory=utc_now)
    note: str = ""


class ConnectorStatus(BaseModel):
    connector: str
    environment: str
    capabilities: dict[str, str]  # AUTH / READ / ANALYTICS / DRAFT / PUBLISH -> CapabilityState
    detail: str = ""


class WorkflowPlan(BaseModel):
    workflow_type: str
    specialists: list[str]
    steps: list[str]
    approval_gates: list[str] = Field(default_factory=list)


class RouteDecision(BaseModel):
    intent: str
    agents: list[str]
    reason: str
    workflow_type: str | None = None


class OrchestratorResult(BaseModel):
    correlation_id: str
    environment: Environment
    result_state: str
    intent: str
    agents: list[str]
    response: str
    records: list[dict[str, Any]] = Field(default_factory=list)
    approval_required: bool = False
    side_effects: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    runtime: str | None = None


class ReadonlySyncResult(BaseModel):
    correlation_id: str | None = None
    state: str
    connector: str
    resource: str
    records: list[dict[str, Any]] = Field(default_factory=list)
    detail: str = ""

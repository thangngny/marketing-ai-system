from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TruthClassification(str, Enum):
    OBSERVED_IN_VIDEO = "OBSERVED_IN_VIDEO"
    ROOT_AUTHOR_CLAIM = "ROOT_AUTHOR_CLAIM"
    ROOT_AUTHOR_REPLY = "ROOT_AUTHOR_REPLY"
    VISIBLE_TEXT = "VISIBLE_TEXT"
    COMMUNITY_REPLY = "COMMUNITY_REPLY"
    OFFICIAL_DOC_VERIFIED = "OFFICIAL_DOC_VERIFIED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class MediaType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    GIF = "gif"
    ARTICLE = "article"
    POLL = "poll"
    AUDIO = "audio"
    NONE = "none"


class ReplyCategory(str, Enum):
    AUTHOR_FOLLOWUP = "AUTHOR_FOLLOWUP"
    TECHNICAL_IMPLEMENTATION = "TECHNICAL_IMPLEMENTATION"
    CORRECTION_OR_DEBUNK = "CORRECTION_OR_DEBUNK"
    QUESTION_ANSWER = "QUESTION_ANSWER"
    FEEDBACK = "FEEDBACK"
    LOW_INFORMATION = "LOW_INFORMATION"


class AuthorInfo(BaseModel):
    id: Optional[str] = None
    name: str = ""
    handle: str = ""
    avatar_url: Optional[str] = None
    verified: Optional[bool] = False
    description: Optional[str] = None


class ExternalLink(BaseModel):
    url: str
    expanded_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    domain: str = ""
    resolved: bool = False
    http_status: Optional[int] = None
    repo_info: Optional[Dict[str, Any]] = None


class MediaItem(BaseModel):
    media_id: Optional[str] = None
    type: MediaType = MediaType.NONE
    url: str = ""
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    local_path: Optional[str] = None
    video_job_id: Optional[str] = None
    summary: Optional[str] = None
    transcription_text: Optional[str] = None


class ReplyNode(BaseModel):
    id: str
    author: AuthorInfo
    text: str
    created_at: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    category: ReplyCategory = ReplyCategory.LOW_INFORMATION
    rank: int = 0
    is_author_reply: bool = False
    reply_to_id: Optional[str] = None
    media: List[MediaItem] = Field(default_factory=list)
    links: List[ExternalLink] = Field(default_factory=list)


class QuoteNode(BaseModel):
    id: str
    author: AuthorInfo
    text: str
    created_at: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    media: List[MediaItem] = Field(default_factory=list)
    links: List[ExternalLink] = Field(default_factory=list)
    perspective: Optional[str] = None


class RootPost(BaseModel):
    id: str
    url: str
    author: AuthorInfo
    text: str
    created_at: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies_count: int = 0
    quotes_count: int = 0
    bookmarks_count: int = 0
    views: Optional[int] = None
    media: List[MediaItem] = Field(default_factory=list)
    links: List[ExternalLink] = Field(default_factory=list)
    is_thread: bool = False
    thread_posts: List[Dict[str, Any]] = Field(default_factory=list)


class ContextGraph(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class CoverageReport(BaseModel):
    status: str = "COMPLETE"  # COMPLETE, PARTIAL, BLOCKED
    replies_reported: int = 0
    replies_retrieved: int = 0
    author_replies_retrieved: int = 0
    quotes_reported: int = 0
    quotes_retrieved: int = 0
    media_reported: int = 0
    media_retrieved: int = 0
    external_links_count: int = 0
    external_links_resolved: int = 0
    resolver_used: str = "STRUCTURED_API"
    truncation_reasons: List[str] = Field(default_factory=list)
    notes: str = ""


class ReproductionStep(BaseModel):
    step_number: int
    name: str
    objective: str
    source_classification: TruthClassification = TruthClassification.INFERRED
    original_command: Optional[str] = None
    windows_command: Optional[str] = None
    verification_command: Optional[str] = None
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH
    requires_approval: bool = False
    status: str = "PLANNED"  # PLANNED, SKIPPED, COMPLETED


class ReproductionPlan(BaseModel):
    job_id: str
    url: str
    demo_objective: str = ""
    prerequisites: List[str] = Field(default_factory=list)
    environment_variables: Dict[str, str] = Field(default_factory=dict)
    steps: List[ReproductionStep] = Field(default_factory=list)
    gap_analysis: Dict[str, Any] = Field(default_factory=dict)
    validation_criteria: List[str] = Field(default_factory=list)
    mode: str = "PLAN_ONLY"


class XContextManifest(BaseModel):
    job_id: str
    url: str
    canonical_url: str
    fetched_at: str
    root: RootPost
    author_followups: List[ReplyNode] = Field(default_factory=list)
    top_replies: List[ReplyNode] = Field(default_factory=list)
    quotes: List[QuoteNode] = Field(default_factory=list)
    graph: ContextGraph = Field(default_factory=ContextGraph)
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    summary: Optional[Dict[str, Any]] = None
    reproduction_plan: Optional[ReproductionPlan] = None

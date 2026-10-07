from __future__ import annotations

import enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class IngestionResolver(str, enum.Enum):
    X_API = "X_API"
    YTDLP = "YTDLP"
    BROWSER = "BROWSER"
    MANUAL_FILE_REQUIRED = "MANUAL_FILE_REQUIRED"


class TruthClassification(str, enum.Enum):
    OBSERVED_IN_VIDEO = "OBSERVED_IN_VIDEO"
    SPOKEN_IN_AUDIO = "SPOKEN_IN_AUDIO"
    VISIBLE_TEXT = "VISIBLE_TEXT"
    INFERRED = "INFERRED"
    VERIFIED_CURRENT = "VERIFIED_CURRENT"
    OUTDATED = "OUTDATED"
    INCOMPATIBLE = "INCOMPATIBLE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    DESTRUCTIVE = "DESTRUCTIVE"


class ExecutionMode(str, enum.Enum):
    ANALYZE_ONLY = "ANALYZE_ONLY"
    PLAN_ONLY = "PLAN_ONLY"
    REPRODUCE_SAFE = "REPRODUCE_SAFE"
    REPRODUCE_FULL = "REPRODUCE_FULL"


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    confidence: float = 0.90
    source: str = "speech"  # speech, auto_caption, visible_text


class SceneInfo(BaseModel):
    scene_id: int
    start: float
    end: float
    keyframe_path: str
    related_transcript: str = ""
    context_hint: str = ""
    cropped_regions: List[str] = Field(default_factory=list)


class FrameMetadata(BaseModel):
    frame_index: int
    timestamp: float
    path: str
    kind: str = "baseline"  # baseline, scene_change, high_density, crop
    category: str = "general"  # terminal, editor, settings, ui, general


class ExtractedStep(BaseModel):
    step_id: int
    start: float = 0.0
    end: float = 0.0
    observed_action: str
    spoken_content: str = ""
    command_candidate: str = ""
    status: TruthClassification = TruthClassification.OBSERVED_IN_VIDEO
    confidence: float = 0.85
    evidence_frames: List[str] = Field(default_factory=list)


class VerificationItem(BaseModel):
    component: str
    video_version: str = "unknown"
    current_version: str = "unknown"
    is_compatible: bool = True
    is_outdated: bool = False
    notes: str = ""
    action_recommendation: str = ""


class ReproductionStep(BaseModel):
    step_id: int
    observed_video_step: str
    verified_current_step: str
    command_or_action: str
    translated_windows_command: str = ""
    files_changed: List[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    rollback_plan: str = ""
    expected_result: str = ""
    execution_status: str = "PENDING"  # PENDING, EXECUTED, SKIPPED, FAILED, BLOCKED_APPROVAL
    actual_result: str = ""


class ReproductionPlan(BaseModel):
    job_id: str
    source_url: str
    demo_objective: str
    demo_architecture: str = ""
    target_os: str = "windows"
    mode: ExecutionMode = ExecutionMode.PLAN_ONLY
    steps: List[ReproductionStep] = Field(default_factory=list)
    verifications: List[VerificationItem] = Field(default_factory=list)
    approval_state: str = "PENDING"  # NOT_REQUIRED, PENDING, APPROVED, REJECTED
    overall_status: str = "PLAN_READY"  # PLAN_READY, PASS, PARTIAL, BLOCKED


class IngestResult(BaseModel):
    job_id: str
    source_url: str
    post_text: str = ""
    author: str = ""
    published_at: str = ""
    duration: float = 0.0
    resolver_used: IngestionResolver
    media_status: str
    transcript_status: str
    frame_status: str
    manifest_path: str
    warnings: List[str] = Field(default_factory=list)


class JobManifest(BaseModel):
    job_id: str
    source_url: str
    created_at: str
    resolver_used: str
    post_text: str = ""
    author: str = ""
    published_at: str = ""
    duration_seconds: float = 0.0
    resolution: str = ""
    fps: float = 0.0
    audio_codec: str = ""
    video_codec: str = ""
    video_checksum: str = ""
    transcript: List[TranscriptSegment] = Field(default_factory=list)
    scenes: List[SceneInfo] = Field(default_factory=list)
    frames: List[FrameMetadata] = Field(default_factory=list)
    extracted_steps: List[ExtractedStep] = Field(default_factory=list)
    extraction_warnings: List[str] = Field(default_factory=list)
    status: str = "COMPLETED"

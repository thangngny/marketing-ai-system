"""
Unified Video Production Engine for Marketing AI System.
Integrates Multi-Modal AI (ElevenLabs, HeyGen, Higgsfield, Pexels, Whisper, HyperFrames, FFmpeg)
into a production-grade automated pipeline with Technology Attribution.
"""

from .attribution import TechnologyAttribution, build_attribution_report
from .composer import VideoComposer, VideoProductionConfig, VideoProductionResult
from .subtitles import SubtitleGenerator
from .stock import StockFootageManager

__all__ = [
    "VideoComposer",
    "VideoProductionConfig",
    "VideoProductionResult",
    "TechnologyAttribution",
    "build_attribution_report",
    "SubtitleGenerator",
    "StockFootageManager",
]

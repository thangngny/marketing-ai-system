from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


class Config:
    def __init__(self, config_dict: Dict[str, Any]):
        self.service_name = config_dict.get("service_name", "x-video-intelligence")
        self.version = config_dict.get("version", "1.0.0")
        self.data_dir = Path(config_dict.get("data_dir", r"C:\Users\Admin\marketing-ai-system\x-video-intelligence\data\jobs"))
        self.reports_dir = Path(config_dict.get("reports_dir", r"C:\Users\Admin\marketing-ai-system\x-video-intelligence\reports"))
        self.ffmpeg_path = config_dict.get("ffmpeg_path", "ffmpeg")
        self.ffprobe_path = config_dict.get("ffprobe_path", "ffprobe")
        self.sampling = config_dict.get("sampling", {})
        self.baseline_fps = float(self.sampling.get("baseline_fps", 1.0))
        self.high_density_fps = float(self.sampling.get("high_density_fps", 4.0))
        self.scene_threshold = float(self.sampling.get("scene_threshold", 0.3))
        self.max_frames_per_job = int(self.sampling.get("max_frames_per_job", 300))
        self.confidence_thresholds = config_dict.get("confidence_thresholds", {})
        self.critical_command_min_confidence = float(self.confidence_thresholds.get("critical_command_min_confidence", 0.90))
        self.noncritical_min_confidence = float(self.confidence_thresholds.get("noncritical_min_confidence", 0.75))
        self.execution = config_dict.get("execution", {})
        self.default_mode = self.execution.get("default_mode", "PLAN_ONLY")
        self.retention = config_dict.get("retention", {})
        self.keep_manifest_days = int(self.retention.get("keep_manifest_days", 30))
        self.keep_raw_media_days = int(self.retention.get("keep_raw_media_days", 7))
        self.max_job_size_mb = int(self.retention.get("max_job_size_mb", 1024))

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.json"


def load_config(config_path: Path | None = None) -> Config:
    path = config_path or _DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    return Config(data)

from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel, Field


class XContextConfig(BaseModel):
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data")
    chrome_executable: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    chrome_profile_dir: str = r"C:\Users\Admin\.buzz\chrome_profiles\Buzz-X-Research"
    x_video_service_dir: Path = Path(r"C:\Users\Admin\marketing-ai-system\x-video-intelligence")
    default_timeout: int = 15
    max_replies_default: int = 25
    max_quotes_default: int = 5
    browser_convergence_scrolls: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    )


def load_config() -> XContextConfig:
    cfg = XContextConfig()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    Path(cfg.chrome_profile_dir).mkdir(parents=True, exist_ok=True)
    return cfg

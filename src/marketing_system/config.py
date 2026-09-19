from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from .constants import Environment


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    environment: Environment = Environment.MOCK
    safe_dry_run: bool = True
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data")
    log_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "logs")

    @field_validator("safe_dry_run", mode="before")
    @classmethod
    def parse_bool(cls, value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    @classmethod
    def from_env(cls) -> "Settings":
        env_file = os.getenv("MARKETING_ENV_FILE")
        if env_file:
            load_dotenv(env_file, override=False)
        else:
            load_dotenv(PROJECT_ROOT / ".env.local", override=False)
        return cls(
            environment=os.getenv("MARKETING_ENVIRONMENT", "mock").lower(),
            safe_dry_run=os.getenv("MARKETING_SAFE_DRY_RUN", "true"),
            data_dir=Path(os.getenv("MARKETING_DATA_DIR") or PROJECT_ROOT / "data"),
            log_dir=Path(os.getenv("MARKETING_LOG_DIR") or PROJECT_ROOT / "logs"),
        )

    def ensure_runtime_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


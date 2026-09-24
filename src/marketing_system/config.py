from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from .constants import Environment


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OWNER_PUBKEY = "057f0407663083746eee6457303cead9fe3eec3bbd39a17214d84c52a9080f2f"


class Settings(BaseModel):
    environment: Environment = Environment.MOCK
    safe_dry_run: bool = True
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data")
    log_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "logs")
    # Public key of the Buzz workspace owner — the only identity whose signed message can approve.
    owner_pubkey: str = OWNER_PUBKEY
    # Buzz channel where approval requests are posted and owner replies are looked for (Welcome).
    buzz_channel: str = "6fdc7c8d-8c62-4308-8228-fc3ec44944bb"

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
            owner_pubkey=os.getenv("MARKETING_OWNER_PUBKEY") or OWNER_PUBKEY,
            buzz_channel=os.getenv("MARKETING_BUZZ_CHANNEL") or "6fdc7c8d-8c62-4308-8228-fc3ec44944bb",
        )

    def ensure_runtime_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


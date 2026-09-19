from __future__ import annotations

from enum import StrEnum


class Environment(StrEnum):
    MOCK = "mock"
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class ConnectorState(StrEnum):
    CONNECTED = "CONNECTED"
    MOCK_READY = "MOCK_READY"
    NEEDS_AUTH = "NEEDS_AUTH"
    NEEDS_ACCESS = "NEEDS_ACCESS"
    CONFIG_REQUIRED = "CONFIG_REQUIRED"
    DISABLED = "DISABLED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


class Impact(StrEnum):
    READ = "READ"
    DRAFT = "DRAFT"
    WRITE = "WRITE"
    HIGH_IMPACT = "HIGH_IMPACT"


class TestState(StrEnum):
    PASS = "PASS"
    PASS_MOCK = "PASS_MOCK"
    SKIPPED_NEEDS_AUTH = "SKIPPED_NEEDS_AUTH"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


SPECIALISTS = (
    "01_strategy",
    "02_market_intelligence",
    "03_account_intelligence",
    "04_content",
    "05_seo_geo",
    "06_sales_copilot",
    "07_campaign",
    "08_kpi_learning",
)


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
    WRITE_LOW_RISK = "WRITE_LOW_RISK"
    WRITE = "WRITE_LOW_RISK"  # legacy alias
    HIGH_IMPACT = "HIGH_IMPACT"


class CapabilityState(StrEnum):
    """Per-capability truth. A service is never just 'connected'."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    MOCK_READY = "MOCK_READY"
    AUTHENTICATING = "AUTHENTICATING"
    NEEDS_MFA = "NEEDS_MFA"
    NEEDS_CAPTCHA = "NEEDS_CAPTCHA"
    NEEDS_ADMIN_APPROVAL = "NEEDS_ADMIN_APPROVAL"
    NEEDS_API_ACCESS = "NEEDS_API_ACCESS"
    LIVE_READ = "LIVE_READ"
    LIVE_DRAFT = "LIVE_DRAFT"
    LIVE_WRITE = "LIVE_WRITE"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class TestState(StrEnum):
    PASS = "PASS"
    PASS_MOCK = "PASS_MOCK"
    PASS_LIVE_READ = "PASS_LIVE_READ"
    PASS_LIVE_DRAFT = "PASS_LIVE_DRAFT"
    NEEDS_AUTH = "NEEDS_AUTH"
    NEEDS_MFA = "NEEDS_MFA"
    NEEDS_API_ACCESS = "NEEDS_API_ACCESS"
    SKIPPED_NEEDS_AUTH = "SKIPPED_NEEDS_AUTH"
    SKIPPED = "SKIPPED"
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


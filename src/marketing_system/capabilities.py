"""Per-capability connector truth (AUTH / READ / ANALYTICS / DRAFT / PUBLISH).

Rules:
- A capability is LIVE_* only with evidence: a successful non-mock call recorded
  in the tool ledger, or a live probe run now.
- Known human-only blockers (MFA, provider product review) are stated explicitly
  instead of a generic NOT_CONFIGURED.
"""

from __future__ import annotations

from .config import Settings
from .constants import CapabilityState as S
from .constants import ConnectorState
from .models import ConnectorStatus

DIMENSIONS = ("AUTH", "READ", "ANALYTICS", "DRAFT", "PUBLISH")

# What the code in this repo can do per connector (independent of credentials).
CODE_SUPPORT: dict[str, set[str]] = {
    "zoho": {"READ"},
    "apollo": set(),
    "m365": {"READ"},
    "website": {"READ", "ANALYTICS"},
    "linkedin": set(),
    "youtube": {"READ", "ANALYTICS"},
    "meta_ads": set(),
    "google_ads": set(),
}

# Verified human-only blockers (INTEGRATION_MATRIX.md, 2026-09-22/24). Applied when credentials are absent.
KNOWN_BLOCKERS: dict[str, tuple[S, str]] = {
    "zoho": (S.NEEDS_MFA, "Zoho API Console needs owner MFA to create the OAuth client."),
    "m365": (S.NEEDS_MFA, "Entra app registration needs owner sign-in with Authenticator."),
    "apollo": (S.NOT_CONFIGURED, "Owner must sign in to Apollo and create a scoped API key."),
    "linkedin": (S.NEEDS_ADMIN_APPROVAL, "App 'Buzz Marketing Hub' created and bound to the Page; waiting for a "
                "Page Admin to approve the app-Page verification link before Community Management API can be requested."),
    "meta_ads": (S.NOT_CONFIGURED, "Meta Business login, app, ads_read token and ad account access missing."),
    "google_ads": (S.NEEDS_ADMIN_APPROVAL, "Account 150-914-5225 is a standard Ads account, not a Manager (MCC); "
                  "API Center refuses developer-token applications from it. Needs a new Manager account linked to it."),
}

PUBLISH_BLOCKERS: dict[str, S] = {
    "linkedin": S.NEEDS_API_ACCESS, "youtube": S.NEEDS_API_ACCESS, "meta_ads": S.NEEDS_API_ACCESS,
    "google_ads": S.NEEDS_API_ACCESS, "website": S.NOT_CONFIGURED, "m365": S.NOT_CONFIGURED,
    "zoho": S.NOT_CONFIGURED, "apollo": S.NOT_CONFIGURED,
}


def connector_status(connector, settings: Settings, store=None, live_probe: bool = False) -> ConnectorStatus:
    name = connector.name
    supported = CODE_SUPPORT.get(name, set())
    caps: dict[str, str] = {}
    if settings.environment.value == "mock":
        for dim in DIMENSIONS:
            caps[dim] = str(S.MOCK_READY)
        return ConnectorStatus(connector=name, environment="mock", capabilities=caps,
                               detail="Deterministic synthetic data; no external calls.")

    report = connector.report(live_probe=live_probe)
    if not report.configured or report.live_state in (ConnectorState.NEEDS_AUTH, ConnectorState.CONFIG_REQUIRED,
                                                      ConnectorState.NEEDS_ACCESS):
        state, detail = KNOWN_BLOCKERS.get(name, (S.NOT_CONFIGURED, report.detail))
        return ConnectorStatus(connector=name, environment=settings.environment.value,
                               capabilities={d: str(state) for d in DIMENSIONS}, detail=detail)

    evidence = store.last_live_success(name) if store is not None else None
    latest = store.last_live_state(name) if store is not None else None
    probed_ok = report.live_tested and report.live_state == ConnectorState.CONNECTED
    if report.live_state == ConnectorState.ERROR:
        auth = S.ERROR
    elif latest and latest[0] not in ("OK", "DUPLICATE") and not probed_ok:
        # The most recent real call failed: last week's success is not today's truth.
        auth = S.AUTHENTICATING if latest[0] == "NEEDS_AUTH" else S.DEGRADED
        evidence = None
    elif probed_ok or evidence:
        auth = S.LIVE_READ
    else:
        auth = S.DEGRADED
    caps["AUTH"] = str(auth)
    for dim in ("READ", "ANALYTICS"):
        if dim not in supported:
            caps[dim] = str(S.NOT_CONFIGURED)
        else:
            caps[dim] = str(S.LIVE_READ if auth is S.LIVE_READ else auth)
    caps["DRAFT"] = str(S.NOT_CONFIGURED if "DRAFT" not in supported else S.DEGRADED)
    caps["PUBLISH"] = str(PUBLISH_BLOCKERS.get(name, S.NOT_CONFIGURED))
    if latest and evidence is None and not probed_ok and latest[0] not in ("OK", "DUPLICATE"):
        detail = f"latest live call {latest[0]} {latest[1]}".strip()
    else:
        detail = f"last live read {evidence}" if evidence else ("live probe OK" if probed_ok else "credentials present; no live evidence yet")
    return ConnectorStatus(connector=name, environment=settings.environment.value, capabilities=caps, detail=detail)

"""Live READ checks through the tool hub (production env from .env.local). Read-only; no writes.

usage: uv run python scripts/live_read_check.py
Prints one line per tool: PASS_LIVE_READ | <state>. Values are summarized, secrets never printed.
"""

from __future__ import annotations

import sys

from marketing_system.app import build_platform
from marketing_system.runtime import get_runtime
from marketing_system.telemetry import new_correlation_id
from marketing_system.tools.hub import ToolContext

CHECKS = [
    ("social.get_channel_metrics", {}, "08_kpi_learning"),
    ("social.get_recent_videos", {"limit": 3}, "04_content"),
    ("website.get_metadata", {}, "04_content"),
    ("website.get_recent_content", {"limit": 3}, "04_content"),
    ("crm.search_leads", {"limit": 5}, "03_account_intelligence"),
    ("prospecting.search_companies", {"limit": 3}, "03_account_intelligence"),
    ("email.get_unread_count", {}, "06_sales_copilot"),
    ("ads.get_campaign_performance", {"platform": "meta"}, "08_kpi_learning"),
    ("analytics.snapshot", {}, "08_kpi_learning"),
]


def main() -> int:
    platform = build_platform(runtime=get_runtime("mock"))
    if platform.settings.environment.value == "mock":
        print("Refusing: environment is mock; live checks need MARKETING_ENVIRONMENT=production (.env.local).")
        return 2
    correlation_id = new_correlation_id()
    print(f"correlation_id={correlation_id} environment={platform.settings.environment.value}")
    for tool, args, specialist in CHECKS:
        result = platform.hub.invoke(tool, args, ToolContext(correlation_id=correlation_id, specialist_id=specialist, runtime="ops"))
        label = "PASS_LIVE_READ" if result.state == "OK" else result.state
        summary = _summary(tool, result.data) if result.state == "OK" else result.detail[:120]
        print(f"{label:<17} {tool:<32} {summary}")
    return 0


def _summary(tool: str, data) -> str:
    if tool == "social.get_channel_metrics":
        return f"channel='{data['channel']}' subscribers={data['subscribers']} videos={data['videos']} views={data['views']}"
    if tool == "social.get_recent_videos":
        return f"{len(data)} videos; latest='{(data[0].get('title') if data else '')}'"
    if tool == "website.get_metadata":
        return f"title='{data[0].get('title')}'"
    if tool == "website.get_recent_content":
        return f"stack={data['stack']} total_posts={data['total']} latest='{data['items'][0]['title'] if data['items'] else ''}'"
    if tool == "analytics.snapshot":
        return f"metrics={[m['name'] for m in data['metrics']]} unavailable={data['unavailable']}"
    return f"{len(data) if hasattr(data, '__len__') else data}"


if __name__ == "__main__":
    sys.exit(main())

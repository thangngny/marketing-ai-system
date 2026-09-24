import asyncio

from mcp import Client
from mcp.client._memory import InMemoryTransport

from marketing_system.mcp_server import server


def test_mcp_tools_are_discoverable_and_callable():
    async def run():
        async with Client(InMemoryTransport(server)) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert "marketing_handle_request" in names
            assert "marketing_system_status" in names
            assert "marketing_sync_readonly" in names
            result = await client.call_tool("marketing_route_intent", {"text": "Viết bài LinkedIn"})
            assert result.is_error is False
            assert result.structured_content["agents"] == ["04_content"]

    asyncio.run(run())


def test_hub_tools_are_namespaced_typed_and_annotated():
    async def run():
        async with Client(InMemoryTransport(server)) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            for name in ("crm_search_leads", "crm_find_existing", "prospecting_search_companies", "email_create_draft",
                         "email_send", "website_get_recent_content", "social_get_recent_videos", "ads_launch_campaign",
                         "analytics_snapshot", "system_connector_status", "workflow_start", "workflow_resume",
                         "approval_status"):
                assert name in tools, name
            assert tools["crm_search_leads"].annotations.read_only_hint is True
            assert tools["email_send"].annotations.destructive_hint is True
            assert tools["email_create_draft"].input_schema["required"] == ["lead_company", "subject", "body"]

    asyncio.run(run())


def test_no_mcp_tool_can_assert_approval():
    async def run():
        async with Client(InMemoryTransport(server)) as client:
            for tool in (await client.list_tools()).tools:
                props = set((tool.input_schema or {}).get("properties", {}))
                assert not props & {"approved", "explicit_approval", "approval", "approve"}, tool.name

    asyncio.run(run())


def test_write_tool_over_mcp_becomes_waiting_workflow():
    async def run():
        async with Client(InMemoryTransport(server)) as client:
            result = await client.call_tool("crm_create_task", {"subject": "Gọi lại", "related_company": "ACME"})
            assert result.structured_content["state"] == "WAITING_APPROVAL"
            assert result.structured_content["approval"]["code"].startswith("MV-")
            resumed = await client.call_tool("workflow_resume", {"workflow_id": result.structured_content["workflow_id"]})
            assert resumed.structured_content["state"] == "WAITING_APPROVAL"  # no owner signature → no progress

    asyncio.run(run())


def test_readonly_sync_is_blocked_in_mock_mode():
    async def run():
        async with Client(InMemoryTransport(server)) as client:
            result = await client.call_tool(
                "marketing_sync_readonly",
                {"connector": "website", "resource": "metadata", "limit": 1},
            )
            assert result.is_error is False
            assert result.structured_content["state"] == "BLOCKED_MOCK_MODE"

    asyncio.run(run())

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
            result = await client.call_tool("marketing_route_intent", {"text": "Viết bài LinkedIn"})
            assert result.is_error is False
            assert result.structured_content["agents"] == ["04_content"]

    asyncio.run(run())


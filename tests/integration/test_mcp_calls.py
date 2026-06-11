"""Integration tests for MCP server tool calls.

These tests verify that MCP tools can be called successfully via HTTP transport.
Tests use the MCP Inspector approach - direct HTTP calls to MCP server.
"""

import asyncio
import os
from typing import Any, Dict, Optional

from fastmcp.exceptions import ToolError

import pytest
from dotenv import load_dotenv

from chat_bot.mcp_server.client.mcp_client import KaitenMCPClient, MCPClientConfig

load_dotenv()

# MCP Server URL from environment or default
MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL", "http://localhost:8000/mcp"
).rstrip("/")
if not MCP_SERVER_URL.endswith("/mcp"):
    MCP_SERVER_URL = MCP_SERVER_URL + "/mcp"


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def mcp_client() -> KaitenMCPClient:
    """Create and initialize MCP client for testing."""
    config = MCPClientConfig(server_url=MCP_SERVER_URL, timeout=30.0)
    client = KaitenMCPClient(config)
    try:
        await client.initialize()
    except Exception as exc:
        pytest.skip(f"MCP server is unavailable at {MCP_SERVER_URL}: {exc}")
    return client


def _extract_first_id_from_text(text: str) -> Optional[int]:
    """Extract the first numeric resource ID from formatted tool output."""
    marker = "(ID: "
    start = text.find(marker)
    if start == -1:
        return None

    start += len(marker)
    end = text.find(")", start)
    if end == -1:
        return None

    raw_id = text[start:end].strip()
    return int(raw_id) if raw_id.isdigit() else None


async def _get_first_space_id(mcp_client: KaitenMCPClient) -> int:
    """Get the first available space ID or skip the test."""
    result = await mcp_client.call_tool("manage_spaces", {"action": "list"})
    text = KaitenMCPClient._extract_text_from_result(result)
    space_id = _extract_first_id_from_text(text)
    if space_id is None:
        pytest.skip("No available spaces found for integration tests")
    return space_id


async def _get_first_board_id(mcp_client: KaitenMCPClient) -> int:
    """Get the first available board ID from the first available space."""
    space_id = await _get_first_space_id(mcp_client)
    result = await mcp_client.call_tool(
        "manage_boards", {"action": "list", "space_id": space_id}
    )
    text = KaitenMCPClient._extract_text_from_result(result)
    board_id = _extract_first_id_from_text(text)
    if board_id is None:
        pytest.skip("No available boards found for integration tests")
    return board_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_server_connection(mcp_client: KaitenMCPClient) -> None:
    """Test that MCP server is accessible."""
    assert mcp_client is not None
    assert mcp_client._initialized is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manage_users_list(mcp_client: KaitenMCPClient) -> None:
    """Test listing users via manage_users tool."""
    result = await mcp_client.call_tool("manage_users", {"action": "list", "limit": 5})
    
    assert result is not None
    # Check that result has text content
    text = KaitenMCPClient._extract_text_from_result(result)
    assert isinstance(text, str)
    assert len(text) > 0
    # Should not be an error
    assert not text.startswith("❌")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manage_spaces_list(mcp_client: KaitenMCPClient) -> None:
    """Test listing spaces via manage_spaces tool."""
    result = await mcp_client.call_tool("manage_spaces", {"action": "list"})
    
    assert result is not None
    text = KaitenMCPClient._extract_text_from_result(result)
    assert isinstance(text, str)
    assert len(text) > 0
    assert not text.startswith("❌")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manage_boards_list(mcp_client: KaitenMCPClient) -> None:
    """Test listing boards via manage_boards tool."""
    space_id = await _get_first_space_id(mcp_client)
    result = await mcp_client.call_tool(
        "manage_boards", {"action": "list", "space_id": space_id}
    )

    assert result is not None
    text = KaitenMCPClient._extract_text_from_result(result)
    assert isinstance(text, str)
    assert len(text) > 0
    is_error = getattr(result, "isError", False)
    assert not is_error, f"Tool returned error: {text}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manage_cards_list(mcp_client: KaitenMCPClient) -> None:
    """Test listing cards via manage_cards tool."""
    result = await mcp_client.call_tool(
        "manage_cards", {"action": "list", "limit": 5}
    )

    assert result is not None
    text = KaitenMCPClient._extract_text_from_result(result)
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manage_columns_list(mcp_client: KaitenMCPClient) -> None:
    """Test listing columns via manage_columns tool."""
    board_id = await _get_first_board_id(mcp_client)
    result = await mcp_client.call_tool(
        "manage_columns", {"action": "list", "board_id": board_id}
    )

    assert result is not None
    text = KaitenMCPClient._extract_text_from_result(result)
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_move_card_structure(mcp_client: KaitenMCPClient) -> None:
    """Test move_card tool structure (may fail without valid IDs, but should handle gracefully)."""
    with pytest.raises(ToolError):
        await mcp_client.call_tool("move_card", {"card_id": 999999, "column_id": 888888})


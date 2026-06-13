"""Tests that MCP tools use documented Kaiten REST API paths and fields."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat_bot.mcp_server.client.kaiten_client import KaitenClient
from chat_bot.mcp_server.config.settings import Settings
from chat_bot.mcp_server.models.time_log import TimeLog
from chat_bot.mcp_server.tools.break_into_tasks import _link_child_card
from chat_bot.mcp_server.tools.manage_columns import _create_column, _update_column
from chat_bot.mcp_server.tools.manage_members import _list_members
from chat_bot.mcp_server.tools.manage_tags import _list_tags, _remove_tag
from chat_bot.mcp_server.tools.manage_time_logs import _list_time_logs, _log_time


@pytest.mark.asyncio
async def test_time_logs_use_hyphenated_api_path() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=[])
    client.post = AsyncMock(return_value={"id": 9})

    await _list_time_logs(client, card_id=12, for_date=None, personal=None, ctx=None)
    await _log_time(
        client,
        card_id=12,
        time_spent=30,
        for_date="2026-06-12",
        role_id=-1,
        comment=None,
        ctx=None,
    )

    client.get.assert_awaited_once_with("cards/12/time-logs")
    client.post.assert_awaited_once_with(
        "cards/12/time-logs",
        {
            "role_id": -1,
            "time_spent": 30,
            "for_date": "2026-06-12",
        },
    )
    assert TimeLog(card_id=12, role_id=-1, time_spent=30, for_date="2026-06-12")


@pytest.mark.asyncio
async def test_card_tags_use_card_tags_endpoint() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=[])
    client.delete = AsyncMock()

    await _list_tags(client, card_id=12, ctx=None)
    await _remove_tag(client, tag_id=7, card_id=12, ctx=None)

    client.get.assert_awaited_once_with("cards/12/tags")
    client.delete.assert_awaited_once_with("cards/12/tags/7")


@pytest.mark.asyncio
async def test_global_tag_delete_is_rejected() -> None:
    client = MagicMock()
    client.delete = AsyncMock()

    with pytest.raises(ValueError, match="card_id is required"):
        await _remove_tag(client, tag_id=7, card_id=None, ctx=None)

    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_child_card_uses_documented_parent_children_endpoint() -> None:
    client = MagicMock()
    client.post = AsyncMock()

    await _link_child_card(client, parent_id=12, child_id=34)

    client.post.assert_awaited_once_with("cards/12/children", {"card_id": 34})


@pytest.mark.asyncio
async def test_columns_send_numeric_type_field() -> None:
    client = MagicMock()
    client.post = AsyncMock(return_value={"id": 4})
    client.patch = AsyncMock(return_value={"id": 4, "title": "Done"})

    await _create_column(client, 2, "Doing", "in_progress", 1, None)
    await _update_column(client, 2, 4, None, "done", None, None)

    client.post.assert_awaited_once_with(
        "boards/2/columns",
        {"title": "Doing", "sort_order": 1, "type": 2},
    )
    client.patch.assert_awaited_once_with("boards/2/columns/4", {"type": 3})


@pytest.mark.asyncio
async def test_member_owner_lookup_uses_users_filter() -> None:
    client = MagicMock()
    client.get = AsyncMock(
        side_effect=[
            [],
            {"id": 12, "owner_id": 7},
            [{"id": 7, "full_name": "Owner"}],
        ]
    )

    result = await _list_members(client, card_id=12, ctx=None)

    assert client.get.await_args_list[2].args == ("users?ids=7",)
    assert result["structured_content"]["owner"]["id"] == 7


@pytest.mark.asyncio
async def test_client_retries_rate_limited_request() -> None:
    settings = Settings(
        kaiten_api_url="https://example.kaiten.ru/api/latest",
        kaiten_api_token="token",
    )
    client = KaitenClient(settings)
    request = httpx.Request("GET", "https://example.kaiten.ru/api/latest/spaces")
    client._client.request = AsyncMock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, request=request),
            httpx.Response(200, json=[], request=request),
        ]
    )

    with patch(
        "chat_bot.mcp_server.client.kaiten_client.asyncio.sleep", AsyncMock()
    ) as sleep:
        response = await client.get("spaces")

    assert response == []
    assert client._client.request.await_count == 2
    sleep.assert_awaited_once()
    await client.close()

"""Tests for manage_cards helper behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_bot.mcp_server.tools.manage_cards import _list_cards


class TestManageCards:
    """Unit tests for card listing filters."""

    @pytest.mark.asyncio
    async def test_list_cards_resolves_owner_name_to_owner_id(self) -> None:
        """Owner name should be resolved before issuing the cards request."""
        client = MagicMock()
        client.get = AsyncMock(return_value=[])

        with patch(
            "chat_bot.mcp_server.tools.manage_cards.find_user_by_name",
            AsyncMock(return_value=77),
        ) as find_user:
            await _list_cards(
                client=client,
                board_id=None,
                board=None,
                space_id=None,
                column_id=None,
                condition=1,
                query=None,
                due_date_after=None,
                due_date_before=None,
                owner_id=None,
                owner_name="efim",
                tag_ids=None,
                limit=50,
                skip=0,
                ctx=None,
            )

        find_user.assert_awaited_once_with(client, "efim")
        client.get.assert_awaited_once_with("cards?condition=1&owner_id=77&limit=50&skip=0")

    @pytest.mark.asyncio
    async def test_list_cards_raises_when_owner_name_is_unknown(self) -> None:
        """Unknown owner_name should fail instead of silently dropping the filter."""
        client = MagicMock()

        with patch(
            "chat_bot.mcp_server.tools.manage_cards.find_user_by_name",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(ValueError, match="User not found: efim"):
                await _list_cards(
                    client=client,
                    board_id=None,
                    board=None,
                    space_id=None,
                    column_id=None,
                    condition=1,
                    query=None,
                    due_date_after=None,
                    due_date_before=None,
                    owner_id=None,
                    owner_name="efim",
                    tag_ids=None,
                    limit=50,
                    skip=0,
                    ctx=None,
                )

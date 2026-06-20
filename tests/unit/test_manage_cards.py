"""Tests for manage_cards helper behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_bot.mcp_server.tools.manage_cards import (
    _list_cards,
    _resolve_board_id,
    _update_card,
)


class TestManageCards:
    """Unit tests for card listing filters."""

    @pytest.mark.asyncio
    async def test_resolve_default_board_in_default_space(self) -> None:
        """Default task board should be resolved inside the jmlc space."""
        client = MagicMock()
        client.get = AsyncMock(
            side_effect=[
                {"spaces": [{"id": 10, "title": "jmlc"}]},
                {"boards": [{"id": 20, "title": "Основная доска"}]},
            ]
        )

        board_id = await _resolve_board_id(
            client=client,
            board_id=None,
            board="Основная доска",
            ctx=None,
        )

        assert board_id == 20
        client.get.assert_any_await("spaces")
        client.get.assert_any_await("spaces/10/boards")

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
        client.get.assert_awaited_once_with(
            "cards?condition=1&owner_id=77&limit=50&offset=0"
        )

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

    @pytest.mark.asyncio
    async def test_update_card_sends_due_date(self) -> None:
        """A due-date-only update must be forwarded to Kaiten."""
        client = MagicMock()
        client.patch = AsyncMock(return_value={"id": 12, "title": "Task"})

        await _update_card(
            client=client,
            card_id=12,
            title=None,
            board=None,
            asap=None,
            due_date="2026-06-14",
            description=None,
            ctx=None,
        )

        client.patch.assert_awaited_once_with(
            "cards/12",
            {"due_date": "2026-06-14"},
        )

    @pytest.mark.asyncio
    async def test_update_card_sends_false_asap_value(self) -> None:
        """Explicit false values must not be dropped from an update."""
        client = MagicMock()
        client.patch = AsyncMock(return_value={"id": 12, "title": "Task"})

        await _update_card(
            client=client,
            card_id=12,
            title=None,
            board=None,
            asap=False,
            due_date=None,
            description=None,
            ctx=None,
        )

        client.patch.assert_awaited_once_with("cards/12", {"asap": False})

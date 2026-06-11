"""Tests for board helper resolution used by natural-language updates."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_bot.mcp_server.tools.helpers import find_board_record_by_name
from chat_bot.mcp_server.tools.manage_boards import _resolve_board_identity


class TestManageBoards:
    """Unit tests for name-based board resolution."""

    @pytest.mark.asyncio
    async def test_find_board_record_by_name_returns_board_and_space_ids(self) -> None:
        """Board lookup should preserve the source space for later updates."""
        client = MagicMock()
        client.get = AsyncMock(
            side_effect=[
                [{"id": 10, "title": "Workspace"}],
                [{"id": 21, "title": "Roadmap"}],
            ]
        )

        result = await find_board_record_by_name(client, "Roadmap")

        assert result is not None
        assert result["id"] == 21
        assert result["space_id"] == 10

    @pytest.mark.asyncio
    async def test_resolve_board_identity_by_board_name_without_space(self) -> None:
        """Update flow should work from a board name alone."""
        client = MagicMock()
        client.get = AsyncMock(
            side_effect=[
                [{"id": 10, "title": "Workspace"}],
                [{"id": 21, "title": "Roadmap"}],
            ]
        )

        space_id, board_id = await _resolve_board_identity(
            client=client,
            board_id=None,
            board="Roadmap",
            space_id=None,
            space=None,
            ctx=None,
        )

        assert space_id == 10
        assert board_id == 21

    @pytest.mark.asyncio
    async def test_resolve_board_identity_by_board_id_fetches_space_from_board(self) -> None:
        """Board ID should be enough for update/delete when board details expose space_id."""
        client = MagicMock()
        client.get = AsyncMock(return_value={"id": 21, "space_id": 10, "title": "Roadmap"})

        space_id, board_id = await _resolve_board_identity(
            client=client,
            board_id=21,
            board=None,
            space_id=None,
            space=None,
            ctx=None,
        )

        assert space_id == 10
        assert board_id == 21

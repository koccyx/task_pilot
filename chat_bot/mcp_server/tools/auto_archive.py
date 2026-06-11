"""Tool for auto-archiving completed cards."""

import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional

from chat_bot.mcp_server.client.kaiten_client import get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from pydantic import Field

from .helpers import find_board_by_name, get_done_columns

logger = logging.getLogger(__name__)


@mcp.tool(
    name="auto_archive",
    description=(
        "Auto-archive completed cards older than specified days. "
        "IMPORTANT: Pass 'board' with board NAME - ID is resolved automatically. "
        "No need to call list first. "
        "Example: auto_archive(board='Sprint 5', days_threshold=14)"
    ),
)
async def auto_archive(
    board_id: Optional[int] = Field(
        None,
        description="Identifier of the board",
        gt=0,
    ),
    board: Optional[str] = Field(
        None,
        description="Board name - automatically resolved to ID, preferred over board_id",
    ),
    days_threshold: int = Field(
        14,
        description="Minimum age in days for archiving",
        ge=0,
    ),
    dry_run: bool = Field(
        False,
        description="Only show what would be archived without executing",
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Auto-archive completed cards.

    Args:
        board_id: Identifier of the board.
        board: Name of the board (alternative to board_id).
        days_threshold: Minimum age in days for archiving.
        dry_run: Only show what would be archived without executing.
        ctx: Logging and progress context.

    Returns:
        dict: Dictionary containing archiving result.

    Raises:
        ValueError: If board not found.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"Auto-archiving cards (dry_run={dry_run})")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    # Resolve board
    resolved_board_id: Optional[int] = board_id
    if board is not None:
        if ctx:
            await ctx.report_progress(progress=10, total=100)
        found_id = await find_board_by_name(client, board)
        if found_id is None:
            raise ValueError(f"Board not found: {board}")
        resolved_board_id = found_id

    if resolved_board_id is None:
        raise ValueError("Either board_id or board must be provided")

    # Get Done columns
    if ctx:
        await ctx.report_progress(progress=20, total=100)
    done_columns = await get_done_columns(client, resolved_board_id)

    if not done_columns:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No Done columns found on the board.",
                }
            ],
            "structured_content": {"archived_count": 0, "card_ids": []},
            "meta": {"operation": "auto_archive", "dry_run": dry_run},
        }

    # Get cards in Done columns
    if ctx:
        await ctx.report_progress(progress=40, total=100)
    cards_response = await client.get(f"cards?board_id={resolved_board_id}&condition=1")
    cards: List[dict]
    if isinstance(cards_response, list):
        cards = cards_response
    elif isinstance(cards_response, dict) and "cards" in cards_response:
        cards = cards_response["cards"]
    else:
        cards = [cards_response] if cards_response else []

    # Filter cards in Done columns
    done_cards = [card for card in cards if card.get("column_id") in done_columns]

    # Filter by age
    threshold_date = (datetime.now() - timedelta(days=days_threshold)).date()
    cards_to_archive = []

    for card in done_cards:
        updated_str = card.get("updated", card.get("updated_at"))
        if updated_str:
            try:
                updated_date = datetime.fromisoformat(
                    updated_str.replace("Z", "+00:00")
                ).date()
                if updated_date <= threshold_date:
                    cards_to_archive.append(card)
            except Exception:
                pass

    if ctx:
        await ctx.report_progress(progress=60, total=100)
        ctx.info(f"Found {len(cards_to_archive)} cards to archive")

    if not cards_to_archive:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"No cards found for archiving (threshold: {days_threshold} days).",
                }
            ],
            "structured_content": {"archived_count": 0, "card_ids": []},
            "meta": {"operation": "auto_archive", "dry_run": dry_run},
        }

    # Archive cards
    archived_ids: List[int] = []
    failed_ids: List[int] = []

    def safe_int(value: Any) -> Optional[int]:
        """Safely convert value to int, returning None if not possible."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    if not dry_run:
        for idx, card in enumerate(cards_to_archive):
            card_id = card.get("id")
            card_id_int = safe_int(card_id)
            if card_id_int is None:
                continue
            try:
                await client.patch(f"cards/{card_id_int}", {"condition": 2})
                archived_ids.append(card_id_int)
                if ctx:
                    await ctx.report_progress(
                        progress=60 + int((idx + 1) / len(cards_to_archive) * 40),
                        total=100,
                    )
            except Exception as e:
                logger.error(f"Failed to archive card {card_id_int}: {e}")
                failed_ids.append(card_id_int)
    else:
        for card in cards_to_archive:
            card_id_int = safe_int(card.get("id"))
            if card_id_int is not None:
                archived_ids.append(card_id_int)

    if ctx:
        await ctx.report_progress(progress=100, total=100)

    mode_text = "Would archive" if dry_run else "Archived"
    response_text = (
        f"{mode_text} {len(archived_ids)} cards:\n"
        f"  • Card IDs: {', '.join(map(str, archived_ids[:10]))}"
        + (f" ... and {len(archived_ids) - 10} more" if len(archived_ids) > 10 else "")
    )

    if failed_ids:
        response_text += f"\n  • Failed: {len(failed_ids)} cards"

    return {
        "content": [{"type": "text", "text": response_text}],
        "structured_content": {
            "archived_count": len(archived_ids),
            "failed_count": len(failed_ids),
            "card_ids": archived_ids,
            "failed_ids": failed_ids,
        },
        "meta": {
            "operation": "auto_archive",
            "board_id": resolved_board_id,
            "days_threshold": days_threshold,
            "dry_run": dry_run,
        },
    }




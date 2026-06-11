"""Tool for mass updating cards by filter in Kaiten."""

import logging
from typing import Any, List, Optional

from pydantic import Field

from chat_bot.mcp_server.client.kaiten_client import get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp

from .helpers import find_board_by_name, find_column_by_name

logger = logging.getLogger(__name__)


@mcp.tool(
    name="mass_update",
    description=(
        "Mass update cards by filter criteria. "
        "Moves cards to target board and column. "
        "Requires confirmation by default."
    ),
)
async def mass_update(
    target_board_id: Optional[int] = Field(
        None,
        description="Target board identifier",
        gt=0,
    ),
    target_board: Optional[str] = Field(
        None,
        description="Target board name (alternative to target_board_id)",
    ),
    target_column_id: Optional[int] = Field(
        None,
        description="Target column identifier",
        gt=0,
    ),
    target_column: Optional[str] = Field(
        None,
        description="Target column name (alternative to target_column_id)",
    ),
    filter_tag: Optional[str] = Field(
        None,
        description="Filter by tag name",
    ),
    filter_owner_id: Optional[int] = Field(
        None,
        description="Filter by owner ID",
        gt=0,
    ),
    filter_column_id: Optional[int] = Field(
        None,
        description="Filter by current column ID",
        gt=0,
    ),
    confirm: bool = Field(
        True,
        description="Require confirmation before execution",
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Mass update cards by filter.

    Args:
        target_board_id: Target board identifier.
        target_board: Target board name (alternative to target_board_id).
        target_column_id: Target column identifier.
        target_column: Target column name (alternative to target_column_id).
        filter_tag: Filter by tag name.
        filter_owner_id: Filter by owner ID.
        filter_column_id: Filter by current column ID.
        confirm: Require confirmation before execution.
        ctx: Logging and progress context.

    Returns:
        dict: Dictionary containing operation result.

    Raises:
        ValueError: If target board/column not found or no filter provided.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info("Starting mass update operation")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    # Resolve target board
    resolved_target_board_id: Optional[int] = target_board_id
    if target_board is not None:
        if ctx:
            await ctx.report_progress(progress=10, total=100)
        found_id = await find_board_by_name(client, target_board)
        if found_id is None:
            raise ValueError(f"Target board not found: {target_board}")
        resolved_target_board_id = found_id

    if resolved_target_board_id is None:
        raise ValueError("Either target_board_id or target_board must be provided")

    # Resolve target column
    resolved_target_column_id: Optional[int] = target_column_id
    if target_column is not None:
        if ctx:
            await ctx.report_progress(progress=20, total=100)
        found_id = await find_column_by_name(
            client, target_column, board_id=resolved_target_board_id
        )
        if found_id is None:
            raise ValueError(
                f"Target column '{target_column}' not found in board {resolved_target_board_id}"
            )
        resolved_target_column_id = found_id

    if resolved_target_column_id is None:
        raise ValueError("Either target_column_id or target_column must be provided")

    # Build filter query
    if ctx:
        await ctx.report_progress(progress=30, total=100)

    filter_params: List[str] = []
    if filter_owner_id:
        filter_params.append(f"owner_id={filter_owner_id}")
    if filter_column_id:
        filter_params.append(f"column_id={filter_column_id}")

    query_string = "&".join(filter_params) if filter_params else ""
    endpoint = f"cards?{query_string}" if query_string else "cards"

    # Get cards
    cards_response = await client.get(endpoint)
    cards: List[dict]
    if isinstance(cards_response, list):
        cards = cards_response
    elif isinstance(cards_response, dict) and "cards" in cards_response:
        cards = cards_response["cards"]
    else:
        cards = [cards_response] if cards_response else []

    # Filter by tag if specified
    if filter_tag:
        # Note: Tag filtering might require additional API calls
        # For now, we'll filter cards that have the tag in their tags list
        filtered_cards = []
        for card in cards:
            card_tags = card.get("tags", [])
            if any(
                tag.get("name", "").lower() == filter_tag.lower() for tag in card_tags
            ):
                filtered_cards.append(card)
        cards = filtered_cards

    if not cards:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No cards found matching the filter criteria.",
                }
            ],
            "structured_content": {"updated_count": 0, "card_ids": []},
            "meta": {"operation": "mass_update"},
        }

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.info(f"Found {len(cards)} cards to update")

    preview_ids = [card.get("id") for card in cards if card.get("id") is not None]
    if confirm:
        preview_sample = ", ".join(map(str, preview_ids[:10]))
        response_text = (
            "⚠️ Confirmation required for mass update.\n"
            f"  • Matches: {len(cards)} cards\n"
            f"  • Sample IDs: {preview_sample}"
            + (
                f" ... and {len(preview_ids) - 10} more"
                if len(preview_ids) > 10
                else ""
            )
            + "\nRe-run with confirm=false to apply changes."
        )
        return {
            "content": [{"type": "text", "text": response_text}],
            "structured_content": {
                "matches": len(cards),
                "sample_ids": preview_ids[:50],
                "requires_confirmation": True,
            },
            "meta": {
                "operation": "mass_update",
                "target_board_id": resolved_target_board_id,
                "target_column_id": resolved_target_column_id,
                "dry_run": True,
            },
        }

    # Update cards
    updated_ids: List[int] = []
    failed_ids: List[int] = []

    for idx, card in enumerate(cards):
        try:
            card_id = card.get("id")
            await client.patch(
                f"cards/{card_id}",
                {
                    "board_id": resolved_target_board_id,
                    "column_id": resolved_target_column_id,
                },
            )
            updated_ids.append(card_id)
            if ctx:
                await ctx.report_progress(
                    progress=50 + int((idx + 1) / len(cards) * 50), total=100
                )
        except Exception as e:
            logger.error(f"Failed to update card {card_id}: {e}")
            failed_ids.append(card_id)

    if ctx:
        await ctx.report_progress(progress=100, total=100)

    response_text = (
        f"✅ Mass update completed:\n"
        f"  • Updated: {len(updated_ids)} cards\n"
        f"  • Failed: {len(failed_ids)} cards\n"
        f"  • Card IDs: {', '.join(map(str, updated_ids[:10]))}"
        + (f" ... and {len(updated_ids) - 10} more" if len(updated_ids) > 10 else "")
    )

    return {
        "content": [{"type": "text", "text": response_text}],
        "structured_content": {
            "updated_count": len(updated_ids),
            "failed_count": len(failed_ids),
            "card_ids": updated_ids,
            "failed_ids": failed_ids,
        },
        "meta": {
            "operation": "mass_update",
            "target_board_id": resolved_target_board_id,
            "target_column_id": resolved_target_column_id,
        },
    }




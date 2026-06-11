"""Tool for moving a card between columns/boards in Kaiten."""

from typing import Any, Optional

from chat_bot.mcp_server.client.kaiten_client import get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from pydantic import Field

from .helpers import find_board_by_name, find_card_by_title, find_column_by_name


@mcp.tool(
    name="move_card",
    description=(
        "Move a card to a different column, board, or lane in Kaiten. "
        "IMPORTANT: Pass 'card' with card TITLE and 'board'/'column' with NAMEs - "
        "all IDs are resolved automatically. No need to search first. "
        "Example: move_card(card='Fix bug', board='Dev Board', column='Done')"
    ),
)
async def move_card(
    card_id: Optional[int] = Field(
        None,
        description="Card ID (use 'card' parameter with title instead for automatic resolution)",
        gt=0,
    ),
    card: Optional[str] = Field(
        None,
        description="Card title - automatically resolved to ID, preferred over card_id",
    ),
    column_id: Optional[int] = Field(
        None,
        description="Identifier of the target column",
        gt=0,
    ),
    column: Optional[str] = Field(
        None,
        description="Column name - automatically resolved to ID, preferred over column_id",
    ),
    board_id: Optional[int] = Field(
        None,
        description="Identifier of the target board (for moving between boards)",
        gt=0,
    ),
    board: Optional[str] = Field(
        None,
        description="Board name - automatically resolved to ID, preferred over board_id",
    ),
    lane_id: Optional[int] = Field(
        None,
        description="Identifier of the target lane",
        gt=0,
    ),
    sort_order: Optional[int] = Field(
        None,
        description="Position in the cell (numeric order)",
        ge=0,
    ),
    position: Optional[int] = Field(
        None,
        description="Position: 1 for first, 2 for last",
        ge=1,
        le=2,
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Move a card to a different column, board, or lane in Kaiten.

    Args:
        card_id: Card identifier (use 'card' parameter instead for auto-resolution).
        card: Card title - automatically resolved to ID.
        column_id: Identifier of the target column.
        column: Name of the target column (alternative to column_id).
        board_id: Identifier of the target board (for moving between boards).
        board: Name of the target board (alternative to board_id).
        lane_id: Identifier of the target lane.
        sort_order: Position in the cell (numeric order).
        position: Position: 1 for first, 2 for last.
        ctx: Logging and progress context.

    Returns:
        dict: Dictionary containing updated card data with structure:
            - content: List with text content
            - structured_content: Updated card data dictionary
            - meta: Metadata about the operation

    Raises:
        ValueError: If no movement parameters provided or column/board not found.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"Moving card: {card_id or card}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    move_data: dict = {}

    # Resolve board name to board_id if needed (do this first for card resolution)
    resolved_board_id: Optional[int] = board_id
    if board is not None:
        if ctx:
            await ctx.report_progress(progress=20, total=100)
            ctx.debug(f"Resolving board name: {board}")

        found_id = await find_board_by_name(client, board)
        if found_id is None:
            error_msg = f"Board not found: {board}"
            if ctx:
                ctx.error(error_msg)
            raise ValueError(error_msg)

        resolved_board_id = found_id
        if ctx:
            ctx.info(f"Board '{board}' resolved to ID: {found_id}")

    if resolved_board_id is not None:
        move_data["board_id"] = resolved_board_id
        if ctx:
            ctx.debug(f"Moving to board_id: {resolved_board_id}")

    # Resolve card title to card_id if needed
    resolved_card_id: Optional[int] = card_id
    if card is not None:
        if ctx:
            await ctx.report_progress(progress=30, total=100)
            ctx.debug(f"Resolving card title: {card}")

        found_card_id = await find_card_by_title(
            client, card, board_id=resolved_board_id
        )
        if found_card_id is None:
            error_msg = f"Card not found: {card}"
            if ctx:
                ctx.error(error_msg)
            raise ValueError(error_msg)

        resolved_card_id = found_card_id
        if ctx:
            ctx.info(f"Card '{card}' resolved to ID: {found_card_id}")

    if resolved_card_id is None:
        error_msg = "Either card_id or card title must be provided"
        if ctx:
            ctx.error(error_msg)
        raise ValueError(error_msg)

    # Resolve column name to column_id if needed
    resolved_column_id: Optional[int] = column_id
    if column is not None:
        if ctx:
            await ctx.report_progress(progress=40, total=100)
            ctx.debug(f"Resolving column name: {column}")

        # Need board_id to find column
        if resolved_board_id is None:
            error_msg = "Board ID or name must be provided when using column name"
            if ctx:
                ctx.error(error_msg)
            raise ValueError(error_msg)

        found_id = await find_column_by_name(client, column, board_id=resolved_board_id)
        if found_id is None:
            error_msg = f"Column '{column}' not found in board {resolved_board_id}"
            if ctx:
                ctx.error(error_msg)
            raise ValueError(error_msg)

        resolved_column_id = found_id
        if ctx:
            ctx.info(
                f"Column '{column}' resolved to ID: {found_id} in board {resolved_board_id}"
            )

    if resolved_column_id is not None:
        move_data["column_id"] = resolved_column_id
        if ctx:
            ctx.debug(f"Moving to column_id: {resolved_column_id}")

    if lane_id is not None:
        move_data["lane_id"] = lane_id
        if ctx:
            ctx.debug(f"Moving to lane_id: {lane_id}")

    if sort_order is not None:
        move_data["sort_order"] = sort_order
        if ctx:
            ctx.debug(f"Setting sort_order: {sort_order}")

    if position is not None:
        move_data["position"] = position
        if ctx:
            ctx.debug(f"Setting position: {position}")

    if not move_data:
        error_msg = (
            "At least one movement parameter must be provided "
            "(column_id/column, board_id/board, lane_id, sort_order, or position)"
        )
        if ctx:
            ctx.warning("No movement parameters provided")
        raise ValueError(error_msg)

    try:
        if ctx:
            await ctx.report_progress(progress=70, total=100)
            ctx.debug("Sending API request")

        response: dict = await client.patch(
            f"cards/{resolved_card_id}",
            move_data,
        )

        if ctx:
            await ctx.report_progress(progress=100, total=100)
            ctx.info(f"Card moved successfully: {resolved_card_id}")

        card_name = response.get("title", "N/A")
        move_description = []
        if resolved_board_id:
            move_description.append(f"board {resolved_board_id}")
        if resolved_column_id:
            move_description.append(f"column {resolved_column_id}")
        if lane_id:
            move_description.append(f"lane {lane_id}")

        move_text = " → ".join(move_description) if move_description else "new position"

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Card '{card_name}' (ID: {resolved_card_id}) moved to {move_text}"
                    ),
                }
            ],
            "structured_content": response,
            "meta": {
                "operation": "move_card",
                "card_id": resolved_card_id,
                "move_data": move_data,
            },
        }
    except Exception as e:
        error_msg = f"Failed to move card: {str(e)}"
        if ctx:
            ctx.error(error_msg)
        raise

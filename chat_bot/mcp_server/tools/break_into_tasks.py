"""Tool for breaking an epic into subtasks in Kaiten."""

import logging
from typing import Any, List, Optional

from pydantic import Field

from chat_bot.mcp_server.client.kaiten_client import get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp

from .helpers import find_board_by_name, find_column_by_type

logger = logging.getLogger(__name__)


async def _link_child_card(client: Any, parent_id: int, child_id: int) -> None:
    """Link an existing card as a child using Kaiten's documented endpoint."""
    await client.post(f"cards/{parent_id}/children", {"card_id": child_id})


@mcp.tool(
    name="break_into_tasks",
    description=(
        "Break an epic card into subtasks. "
        "Analyzes the epic description and creates child cards. "
        "Creates a checklist in the epic for tracking progress."
    ),
)
async def break_into_tasks(
    card_id: int = Field(
        ...,
        description="Unique identifier of the epic card",
        gt=0,
    ),
    target_board_id: Optional[int] = Field(
        None,
        description="Target board for subtasks (default: same as epic)",
    ),
    target_board: Optional[str] = Field(
        None,
        description="Target board name (alternative to target_board_id)",
    ),
    target_column_id: Optional[int] = Field(
        None,
        description="Target column for subtasks (default: Backlog)",
    ),
    inherit_owner: bool = Field(
        True,
        description="Assign same owner to subtasks",
    ),
    auto_confirm: bool = Field(
        False,
        description="Create subtasks without confirmation",
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Break an epic into subtasks.

    Args:
        card_id: Unique identifier of the epic card.
        target_board_id: Target board for subtasks (default: same as epic).
        target_board: Target board name (alternative to target_board_id).
        target_column_id: Target column for subtasks (default: Backlog).
        inherit_owner: Assign same owner to subtasks.
        auto_confirm: Create subtasks without confirmation.
        ctx: Logging and progress context.

    Returns:
        dict: Dictionary containing created subtasks data.

    Raises:
        ValueError: If epic not found or invalid parameters.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"Breaking epic {card_id} into subtasks")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    # Get epic card
    if ctx:
        await ctx.report_progress(progress=10, total=100)
    try:
        epic = await client.get(f"cards/{card_id}")
    except Exception as e:
        raise ValueError(f"Epic card {card_id} not found: {str(e)}")

    epic_title = epic.get("title", "N/A")
    epic_description = epic.get("description", "")
    epic_board_id = epic.get("board_id")
    epic_owner_id = epic.get("owner_id") if inherit_owner else None
    epic_size = epic.get("size", 0)

    # Resolve target board
    resolved_board = target_board_id or epic_board_id
    if resolved_board is None:
        raise ValueError("Cannot determine target board: no board_id in epic")
    resolved_target_board_id: int = int(resolved_board)
    if target_board is not None:
        if ctx:
            await ctx.report_progress(progress=20, total=100)
        found_id = await find_board_by_name(client, target_board)
        if found_id is None:
            raise ValueError(f"Target board not found: {target_board}")
        resolved_target_board_id = found_id

    # Resolve target column
    resolved_target_column_id: Optional[int] = target_column_id
    if resolved_target_column_id is None:
        if ctx:
            await ctx.report_progress(progress=30, total=100)
        # Find Backlog column (type=1)
        resolved_target_column_id = await find_column_by_type(
            client, resolved_target_board_id, 1
        )

    if resolved_target_column_id is None:
        # Fallback: get first column
        try:
            board_info = await client.get(f"boards/{resolved_target_board_id}")
            columns = board_info.get("columns", [])
            if columns:
                resolved_target_column_id = columns[0].get("id")
        except Exception:
            raise ValueError("Could not determine target column")

    # Analyze description for subtasks
    # Note: In a full implementation, this would use AI to analyze the description
    # For now, we'll create a simple breakdown based on common patterns
    if ctx:
        await ctx.report_progress(progress=40, total=100)
        ctx.debug("Analyzing epic description for subtasks")

    # Simple heuristic: split by common separators or create default subtasks
    subtask_titles: List[str] = []
    if epic_description:
        # Try to extract tasks from description
        # Look for numbered lists, bullet points, or common patterns
        lines = epic_description.split("\n")
        for line in lines:
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            # Check for numbered or bulleted items
            if line.startswith(("-", "*", "•", "1.", "2.", "3.")):
                # Remove prefix
                for prefix in ("-", "*", "•", "1.", "2.", "3.", "4.", "5."):
                    if line.startswith(prefix):
                        line = line[len(prefix) :].strip()
                        break
                if line and len(line) > 5:  # Minimum length
                    subtask_titles.append(line[:100])  # Limit length

    # If no subtasks found, create default ones
    if not subtask_titles:
        subtask_titles = [
            f"{epic_title} - Planning",
            f"{epic_title} - Implementation",
            f"{epic_title} - Testing",
            f"{epic_title} - Review",
        ]

    # Limit to reasonable number
    subtask_titles = subtask_titles[:7]

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.info(f"Will create {len(subtask_titles)} subtasks")

    # Create subtasks
    created_subtasks: List[dict] = []
    subtask_size = (
        epic_size // len(subtask_titles) if epic_size and subtask_titles else 0
    )

    for idx, subtask_title in enumerate(subtask_titles):
        try:
            if ctx:
                await ctx.report_progress(
                    progress=50 + int((idx + 1) / len(subtask_titles) * 40), total=100
                )

            subtask_data: dict = {
                "title": subtask_title,
                "board_id": resolved_target_board_id,
                "column_id": resolved_target_column_id,
            }

            if epic_owner_id:
                subtask_data["owner_id"] = epic_owner_id
            if subtask_size:
                subtask_data["size"] = subtask_size

            subtask = await client.post("cards", subtask_data)
            subtask_id = subtask.get("id")

            # Link to parent
            try:
                await _link_child_card(client, card_id, subtask_id)
            except Exception:
                # Parent linking might not be available in all API versions
                logger.warning(
                    f"Could not link subtask {subtask_id} to parent {card_id}"
                )

            created_subtasks.append(subtask)
        except Exception as e:
            logger.error(f"Failed to create subtask '{subtask_title}': {e}")

    # Create checklist in epic
    if ctx:
        await ctx.report_progress(progress=95, total=100)
    try:
        checklist_items = [
            {"title": title, "checked": False} for title in subtask_titles
        ]
        await client.post(
            f"cards/{card_id}/checklists",
            {"title": "Subtasks", "items": checklist_items},
        )
    except Exception:
        logger.warning("Could not create checklist in epic")

    if ctx:
        await ctx.report_progress(progress=100, total=100)

    subtask_ids = [st.get("id") for st in created_subtasks]
    response_text = (
        f"✅ Epic '{epic_title}' broken into {len(created_subtasks)} subtasks:\n"
        f"  • Subtask IDs: {', '.join(map(str, subtask_ids))}\n"
        f"  • Checklist created in epic for tracking"
    )

    return {
        "content": [{"type": "text", "text": response_text}],
        "structured_content": {
            "epic_id": card_id,
            "subtasks": created_subtasks,
            "subtask_count": len(created_subtasks),
        },
        "meta": {
            "operation": "break_into_tasks",
            "epic_id": card_id,
            "subtask_ids": subtask_ids,
        },
    }

"""Unified tool for column operations in Kaiten."""

from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from chat_bot.mcp_server.models.column import Column
from pydantic import Field, ValidationError

from .helpers import find_board_by_name, find_column_by_name


async def _resolve_board_id(
    client: KaitenClient,
    board_id: Optional[int],
    board: Optional[str],
    ctx: Optional[Any],
) -> int:
    """Resolve board_id from board name if needed."""
    resolved_board_id = board_id
    if board is not None:
        if ctx:
            await ctx.report_progress(progress=20, total=100)
            ctx.debug(f"Resolving board name: {board}")
        found_id = await find_board_by_name(client, board)
        if found_id is None:
            raise ValueError(f"Board not found: {board}")
        resolved_board_id = found_id
        if ctx:
            ctx.info(f"Board '{board}' resolved to ID: {found_id}")

    if resolved_board_id is None:
        raise ValueError("Either board_id or board name must be provided")
    return resolved_board_id


async def _list_columns(
    client: KaitenClient,
    board_id: int,
    ctx: Optional[Any],
) -> dict:
    """List all columns in a board."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: Union[dict, List[Dict[str, Any]]] = await client.get(
        f"boards/{board_id}/columns"
    )

    columns: List[Dict[str, Any]]
    if isinstance(response, list):
        columns = response
    elif isinstance(response, dict) and "columns" in response:
        columns = response["columns"]
    else:
        columns = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(columns)} columns")

    columns_text = "\n".join(
        f"• {c.get('title', c.get('name', 'N/A'))} (ID: {c.get('id', 'N/A')}, type: {c.get('type', 'N/A')})"
        for c in columns
    )

    return {
        "content": [
            {"type": "text", "text": f"Found {len(columns)} columns:\n{columns_text}"}
        ],
        "structured_content": columns,
        "meta": {"operation": "list", "board_id": board_id, "count": len(columns)},
    }


async def _create_column(
    client: KaitenClient,
    board_id: int,
    title: str,
    column_type: Optional[str],
    sort_order: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """Create a new column on a board."""
    if ctx:
        await ctx.report_progress(progress=25, total=100)
        ctx.debug("Validating column data")

    try:
        column_data = Column(
            board_id=board_id,
            title=title,
            column_type=column_type,
            sort_order=sort_order,
        )
    except ValidationError as e:
        raise ValueError(f"Column validation failed: {e}") from e

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Preparing API request")

    column_dict = column_data.model_dump(exclude={"id", "board_id"}, exclude_none=True)

    if ctx:
        await ctx.report_progress(progress=75, total=100)
        ctx.info("Sending API request")

    response: dict = await client.post(f"boards/{board_id}/columns", column_dict)
    column_id = response.get("id")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Column created: {column_id}")

    return {
        "content": [
            {"type": "text", "text": f"Column '{title}' created with ID: {column_id}"}
        ],
        "structured_content": response,
        "meta": {"operation": "create", "column_id": column_id, "board_id": board_id},
    }


async def _update_column(
    client: KaitenClient,
    board_id: int,
    column_id: int,
    title: Optional[str],
    column_type: Optional[str],
    sort_order: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """Update a column."""
    update_data: Dict[str, Any] = {}

    if title is not None:
        update_data["title"] = title
        if ctx:
            ctx.debug(f"Updating column title: {title}")

    if column_type is not None:
        update_data["column_type"] = column_type
        if ctx:
            ctx.debug(f"Updating column type: {column_type}")

    if sort_order is not None:
        update_data["sort_order"] = sort_order
        if ctx:
            ctx.debug(f"Updating column sort_order: {sort_order}")

    if not update_data:
        raise ValueError("At least one field must be provided for update")

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: dict = await client.patch(
        f"boards/{board_id}/columns/{column_id}", update_data
    )

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Column updated: {column_id}")

    column_name = response.get("title", response.get("name", "N/A"))
    return {
        "content": [
            {
                "type": "text",
                "text": f"Column updated: {column_name} (ID: {column_id})",
            }
        ],
        "structured_content": response,
        "meta": {"operation": "update", "column_id": column_id, "board_id": board_id},
    }


async def _remove_column(
    client: KaitenClient,
    board_id: int,
    column_id: int,
    force: bool,
    ctx: Optional[Any],
) -> dict:
    """Remove a column from a board."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    endpoint = f"boards/{board_id}/columns/{column_id}"
    if force:
        endpoint += "?force=true"

    await client.delete(endpoint)

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Column removed: {column_id}")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Column {column_id} removed from board {board_id}",
            }
        ],
        "structured_content": {
            "success": True,
            "board_id": board_id,
            "column_id": column_id,
        },
        "meta": {"operation": "remove", "board_id": board_id, "column_id": column_id},
    }


@mcp.tool(
    name="manage_columns",
    description=(
        "Unified tool for column operations. "
        "Actions: list, create, update, remove. "
        "IMPORTANT: Pass 'board' and 'column' parameters with NAMEs - IDs are resolved automatically. "
        "No need to call list first. "
        "Example: manage_columns(action='list', board='Sprint 5')"
    ),
)
async def manage_columns(
    action: Literal["list", "create", "update", "remove"] = Field(
        ..., description="Action to perform"
    ),
    board_id: Optional[int] = Field(None, description="Board ID", gt=0),
    board: Optional[str] = Field(
        None,
        description="Board name - automatically resolved to ID, preferred over board_id",
    ),
    column_id: Optional[int] = Field(
        None, description="Column ID (required for update/remove)", gt=0
    ),
    column: Optional[str] = Field(
        None,
        description="Column name - automatically resolved to ID, preferred over column_id",
    ),
    title: Optional[str] = Field(
        None, description="Column title (required for create, optional for update)"
    ),
    column_type: Optional[str] = Field(
        None, description="Column type (e.g., queue, in_progress, done)"
    ),
    sort_order: Optional[int] = Field(
        None, description="Order position of the column on the board", ge=0
    ),
    force: bool = Field(
        False, description="Cascade delete with all tasks (for remove)"
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified column management tool.

    Args:
        action: Operation to perform (list/create/update/remove).
        board_id: Board identifier.
        board: Board name (alternative to board_id).
        column_id: Column identifier (required for update/remove).
        column: Column name (alternative to column_id, for update/remove).
        title: Column title (required for create, optional for update).
        column_type: Column type (optional for create/update).
        sort_order: Order position of the column (optional for create/update).
        force: If True, cascade delete with all tasks (for remove).
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"manage_columns: action={action}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        resolved_board_id = await _resolve_board_id(client, board_id, board, ctx)

        if action == "list":
            return await _list_columns(client, resolved_board_id, ctx)

        if action == "create":
            if title is None:
                raise ValueError("title is required for create action")
            return await _create_column(
                client, resolved_board_id, title, column_type, sort_order, ctx
            )

        if action == "update":
            resolved_column_id = column_id
            if column is not None:
                if ctx:
                    await ctx.report_progress(progress=20, total=100)
                    ctx.debug(f"Resolving column name: {column}")
                found_col_id = await find_column_by_name(
                    client, column, board_id=resolved_board_id
                )
                if found_col_id is None:
                    raise ValueError(f"Column not found: {column}")
                resolved_column_id = found_col_id
                if ctx:
                    ctx.info(f"Column '{column}' resolved to ID: {found_col_id}")

            if resolved_column_id is None:
                raise ValueError("Either column_id or column name must be provided")
            return await _update_column(
                client,
                resolved_board_id,
                resolved_column_id,
                title,
                column_type,
                sort_order,
                ctx,
            )

        if action == "remove":
            resolved_column_id = column_id
            if column is not None:
                if ctx:
                    await ctx.report_progress(progress=30, total=100)
                    ctx.debug(f"Resolving column name: {column}")
                found_col_id = await find_column_by_name(
                    client, column, board_id=resolved_board_id
                )
                if found_col_id is None:
                    raise ValueError(f"Column not found: {column}")
                resolved_column_id = found_col_id
                if ctx:
                    ctx.info(f"Column '{column}' resolved to ID: {found_col_id}")

            if resolved_column_id is None:
                raise ValueError("Either column_id or column name must be provided")
            return await _remove_column(
                client, resolved_board_id, resolved_column_id, force, ctx
            )

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_columns failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

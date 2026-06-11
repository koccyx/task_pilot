"""Unified tool for board operations in Kaiten."""

from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from chat_bot.mcp_server.models.board import Board
from pydantic import Field, ValidationError

from .helpers import find_board_record_by_name, find_space_by_name


async def _resolve_space_id(
    client: KaitenClient,
    space_id: Optional[int],
    space: Optional[str],
    ctx: Optional[Any],
) -> int:
    """Resolve space_id from space name if needed."""
    resolved_space_id = space_id
    if space is not None:
        if ctx:
            await ctx.report_progress(progress=20, total=100)
            ctx.debug(f"Resolving space name: {space}")
        found_id = await find_space_by_name(client, space)
        if found_id is None:
            raise ValueError(f"Space not found: {space}")
        resolved_space_id = found_id
        if ctx:
            ctx.info(f"Space '{space}' resolved to ID: {found_id}")

    if resolved_space_id is None:
        raise ValueError("Either space_id or space name must be provided")
    return resolved_space_id


async def _resolve_board_identity(
    client: KaitenClient,
    board_id: Optional[int],
    board: Optional[str],
    space_id: Optional[int],
    space: Optional[str],
    ctx: Optional[Any],
) -> tuple[int, int]:
    """Resolve both space_id and board_id for board updates and deletes.

    Natural-language requests often contain only the board name or only board_id.
    This helper makes mutating operations executable without asking the user for
    redundant hierarchy details when Kaiten can resolve them.
    """
    resolved_board_id = board_id
    resolved_space_id = space_id

    if board is not None:
        if ctx:
            await ctx.report_progress(progress=20, total=100)
            ctx.debug(f"Resolving board name: {board}")
        board_record = await find_board_record_by_name(client, board)
        if board_record is None:
            raise ValueError(f"Board not found: {board}")
        resolved_board_id = board_record.get("id")
        resolved_space_id = resolved_space_id or board_record.get("space_id")
        if ctx:
            ctx.info(
                f"Board '{board}' resolved to ID: {resolved_board_id}, "
                f"space ID: {resolved_space_id}"
            )

    if resolved_board_id is None:
        raise ValueError("Either board_id or board name must be provided")

    if resolved_space_id is None and space is not None:
        resolved_space_id = await _resolve_space_id(client, None, space, ctx)

    if resolved_space_id is None:
        if ctx:
            await ctx.report_progress(progress=35, total=100)
            ctx.debug(f"Fetching board details for board_id={resolved_board_id}")
        board_response: dict = await client.get(f"boards/{resolved_board_id}")
        resolved_space_id = board_response.get("space_id")
        if ctx and resolved_space_id is not None:
            ctx.info(
                f"Board {resolved_board_id} resolved to space ID: {resolved_space_id}"
            )

    if resolved_space_id is None:
        raise ValueError(
            "Unable to resolve space for board update/delete. "
            "Pass board name, space name, or a board_id with accessible board details."
        )

    return resolved_space_id, resolved_board_id


async def _list_boards(
    client: KaitenClient,
    space_id: int,
    ctx: Optional[Any],
) -> dict:
    """List all boards in a space."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: Union[dict, List[Dict[str, Any]]] = await client.get(
        f"spaces/{space_id}/boards"
    )

    boards: List[Dict[str, Any]]
    if isinstance(response, list):
        boards = response
    elif isinstance(response, dict) and "boards" in response:
        boards = response["boards"]
    else:
        boards = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(boards)} boards")

    boards_text = "\n".join(
        f"• {b.get('title', b.get('name', 'N/A'))} (ID: {b.get('id', 'N/A')})"
        for b in boards
    )

    return {
        "content": [
            {"type": "text", "text": f"Found {len(boards)} boards:\n{boards_text}"}
        ],
        "structured_content": boards,
        "meta": {"operation": "list", "space_id": space_id, "count": len(boards)},
    }


async def _create_board(
    client: KaitenClient,
    space_id: int,
    title: str,
    description: Optional[str],
    ctx: Optional[Any],
) -> dict:
    """Create a new board."""
    if ctx:
        await ctx.report_progress(progress=40, total=100)
        ctx.debug("Validating board data")

    try:
        board_data = Board(title=title, space_id=space_id, description=description)
    except ValidationError as e:
        raise ValueError(f"Board validation failed: {e}") from e

    if ctx:
        await ctx.report_progress(progress=60, total=100)
        ctx.debug("Preparing API request")

    board_dict = board_data.model_dump(exclude={"id", "space_id"}, exclude_none=True)

    if ctx:
        await ctx.report_progress(progress=80, total=100)
        ctx.info("Sending API request")

    response: dict = await client.post(f"spaces/{space_id}/boards", board_dict)
    board_id = response.get("id")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Board created: {board_id}")

    return {
        "content": [
            {"type": "text", "text": f"Board '{title}' created with ID: {board_id}"}
        ],
        "structured_content": response,
        "meta": {"operation": "create", "board_id": board_id},
    }


async def _update_board(
    client: KaitenClient,
    space_id: int,
    board_id: int,
    title: Optional[str],
    description: Optional[str],
    ctx: Optional[Any],
) -> dict:
    """Update a board."""
    update_data: Dict[str, Any] = {}

    if title is not None:
        update_data["title"] = title
        if ctx:
            ctx.debug(f"Updating board title: {title}")

    if description is not None:
        update_data["description"] = description
        if ctx:
            ctx.debug(f"Updating board description: {description}")

    if not update_data:
        raise ValueError("At least one field must be provided for update")

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: dict = await client.patch(
        f"spaces/{space_id}/boards/{board_id}", update_data
    )

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Board updated: {board_id}")

    board_name = response.get("title", response.get("name", "N/A"))
    return {
        "content": [
            {"type": "text", "text": f"Board updated: {board_name} (ID: {board_id})"}
        ],
        "structured_content": response,
        "meta": {"operation": "update", "board_id": board_id},
    }


async def _delete_board(
    client: KaitenClient,
    space_id: int,
    board_id: int,
    ctx: Optional[Any],
) -> dict:
    """Delete a board."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    await client.delete(f"spaces/{space_id}/boards/{board_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Board deleted: {board_id}")

    return {
        "content": [{"type": "text", "text": f"Board {board_id} deleted"}],
        "structured_content": {"status": "deleted", "board_id": board_id},
        "meta": {"operation": "delete", "board_id": board_id},
    }


@mcp.tool(
    name="manage_boards",
    description=(
        "Unified tool for board operations. "
        "Actions: list, create, update, delete. "
        "IMPORTANT: For create/list pass 'space' with the space NAME. "
        "For update/delete you can pass either 'board' with board NAME or 'board_id'; "
        "space is resolved automatically when possible. "
        "No need to call list first. "
        "Example: manage_boards(action='update', board='Marketing roadmap', title='Q2 roadmap')"
    ),
)
async def manage_boards(
    action: Literal["list", "create", "update", "delete"] = Field(
        ..., description="Action to perform"
    ),
    board_id: Optional[int] = Field(
        None, description="Board ID (required for update/delete)", gt=0
    ),
    board: Optional[str] = Field(
        None,
        description="Board name - automatically resolved to board_id and space_id, preferred for update/delete",
    ),
    space_id: Optional[int] = Field(None, description="Space ID", gt=0),
    space: Optional[str] = Field(
        None,
        description="Space name - automatically resolved to ID, preferred over space_id",
    ),
    title: Optional[str] = Field(
        None, description="Board title (required for create, optional for update)"
    ),
    description: Optional[str] = Field(
        None, description="Board description (for create/update)"
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified board management tool.

    Args:
        action: Operation to perform (list/create/update/delete).
        board_id: Board identifier (required for update/delete if board name omitted).
        board: Board name (alternative to board_id for update/delete).
        space_id: Space identifier (required for list/create if space omitted).
        space: Space name (alternative to space_id, required for list/create).
        title: Board title (required for create, optional for update).
        description: Board description (for create/update).
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"manage_boards: action={action}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        if action == "list":
            resolved_space_id = await _resolve_space_id(client, space_id, space, ctx)
            return await _list_boards(client, resolved_space_id, ctx)

        if action == "create":
            if title is None:
                raise ValueError("title is required for create action")
            resolved_space_id = await _resolve_space_id(client, space_id, space, ctx)
            return await _create_board(
                client, resolved_space_id, title, description, ctx
            )

        if action == "update":
            resolved_space_id, resolved_board_id = await _resolve_board_identity(
                client=client,
                board_id=board_id,
                board=board,
                space_id=space_id,
                space=space,
                ctx=ctx,
            )
            return await _update_board(
                client, resolved_space_id, resolved_board_id, title, description, ctx
            )

        if action == "delete":
            resolved_space_id, resolved_board_id = await _resolve_board_identity(
                client=client,
                board_id=board_id,
                board=board,
                space_id=space_id,
                space=space,
                ctx=ctx,
            )
            return await _delete_board(client, resolved_space_id, resolved_board_id, ctx)

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_boards failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

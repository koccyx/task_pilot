"""Unified tool for card operations in Kaiten."""

from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.logging_config import get_logger, log_intermediate_call, log_method_call
from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from chat_bot.mcp_server.models.card import Card
from pydantic import Field, ValidationError

from .helpers import find_board_by_name, find_space_by_name, find_user_by_name

logger = get_logger(__name__)

DEFAULT_TASK_SPACE_NAME = "jmlc"
DEFAULT_TASK_BOARD_NAME = "основная доска"


async def _find_board_in_space(
    client: KaitenClient,
    space_name: str,
    board_name: str,
) -> Optional[int]:
    """Find a board by name inside a concrete space."""
    space_id = await find_space_by_name(client, space_name)
    if space_id is None:
        return None

    boards_response = await client.get(f"spaces/{space_id}/boards")
    if isinstance(boards_response, list):
        boards = boards_response
    elif isinstance(boards_response, dict) and "boards" in boards_response:
        boards = boards_response["boards"]
    elif isinstance(boards_response, dict) and "data" in boards_response:
        boards = boards_response["data"]
    else:
        boards = [boards_response] if boards_response else []

    board_name_lower = board_name.lower()
    for board_record in boards:
        if not isinstance(board_record, dict):
            continue
        for field in ("title", "name"):
            value = board_record.get(field)
            if isinstance(value, str) and value.lower() == board_name_lower:
                board_id = board_record.get("id")
                return board_id if isinstance(board_id, int) else None
    return None


@log_method_call(log_input=True, log_output=True, log_errors=True)
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
            ctx.debug(f"Resolving board name: {board}")
        board_name = board.strip()
        if board_name.lower() == DEFAULT_TASK_BOARD_NAME:
            with log_intermediate_call(
                logger,
                "_find_board_in_space",
                space_name=DEFAULT_TASK_SPACE_NAME,
                board_name=board,
            ):
                found_id = await _find_board_in_space(
                    client,
                    DEFAULT_TASK_SPACE_NAME,
                    board,
                )
        else:
            with log_intermediate_call(logger, "find_board_by_name", board_name=board):
                found_id = await find_board_by_name(client, board)
        if found_id is None:
            error_msg = f"Board not found: {board}"
            logger.error(
                error_msg,
                extra={
                    "method_name": "_resolve_board_id",
                    "error_type": "ValueError",
                    "error_message": error_msg,
                },
            )
            raise ValueError(error_msg)
        resolved_board_id = found_id
        if ctx:
            ctx.info(f"Board '{board}' resolved to ID: {found_id}")

    if resolved_board_id is None:
        error_msg = "Either board_id or board must be provided"
        logger.error(
            error_msg,
            extra={
                "method_name": "_resolve_board_id",
                "error_type": "ValueError",
                "error_message": error_msg,
            },
        )
        raise ValueError(error_msg)
    return resolved_board_id


@log_method_call(log_input=True, log_output=True, log_errors=True)
async def _create_card(
    client: KaitenClient,
    title: str,
    board_id: int,
    asap: bool,
    due_date: Optional[str],
    description: Optional[str],
    ctx: Optional[Any],
) -> dict:
    """Create a new card in Kaiten."""
    if ctx:
        ctx.debug("Validating card data")

    try:
        with log_intermediate_call(
            logger, "Card.__init__", title=title, board_id=board_id
        ):
            card_data = Card(
                title=title,
                board_id=board_id,
                asap=asap,
                due_date=due_date,
                description=description,
            )
    except ValidationError as e:
        error_msg = f"Card validation failed: {e}"
        logger.error(
            error_msg,
            extra={
                "method_name": "_create_card",
                "error_type": "ValidationError",
                "error_message": str(e),
            },
            exc_info=True,
        )
        if ctx:
            ctx.error(error_msg)
        raise

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Preparing API request")

    card_dict = card_data.model_dump(exclude={"id"}, exclude_none=True)

    if ctx:
        await ctx.report_progress(progress=75, total=100)
        ctx.info("Sending API request")

    with log_intermediate_call(logger, "client.post", endpoint="cards"):
        response: dict = await client.post("cards", card_dict)
    card_id = response.get("id")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Card created successfully: {card_id}")

    result = {
        "content": [{"type": "text", "text": f"Card created with ID: {card_id}"}],
        "structured_content": response,
        "meta": {"operation": "create", "card_id": card_id},
    }
    return result


async def _get_card(
    client: KaitenClient,
    card_id: int,
    ctx: Optional[Any],
) -> dict:
    """Get a card from Kaiten by ID."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: dict = await client.get(f"cards/{card_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Card retrieved: {card_id}")

    card_name = response.get("title", "N/A")
    return {
        "content": [{"type": "text", "text": f"Card retrieved: {card_name}"}],
        "structured_content": response,
        "meta": {"operation": "get", "card_id": card_id},
    }


async def _update_card(
    client: KaitenClient,
    card_id: int,
    title: Optional[str],
    board: Optional[Union[int, str]],
    asap: Optional[bool],
    due_date: Optional[str],
    description: Optional[str],
    ctx: Optional[Any],
) -> dict:
    """Update a card in Kaiten."""
    update_data: Dict[str, Any] = {}

    if title is not None:
        update_data["title"] = title
        if ctx:
            ctx.debug(f"Updating card title: {title}")

    if board is not None:
        if isinstance(board, str):
            if ctx:
                await ctx.report_progress(progress=20, total=100)
                ctx.debug(f"Resolving board name: {board}")
            found_id = await find_board_by_name(client, board)
            if found_id is None:
                raise ValueError(f"Board not found: {board}")
            update_data["board_id"] = found_id
            if ctx:
                ctx.info(f"Board '{board}' resolved to ID: {found_id}")
        else:
            update_data["board_id"] = board
            if ctx:
                ctx.debug(f"Updating card board_id: {board}")

    if description is not None:
        update_data["description"] = description
        if ctx:
            ctx.debug(f"Updating card description: {description}")

    if asap is not None:
        update_data["asap"] = asap
        if ctx:
            ctx.debug(f"Updating card asap: {asap}")

    if due_date is not None:
        update_data["due_date"] = due_date
        if ctx:
            ctx.debug(f"Updating card due_date: {due_date}")

    if not update_data:
        raise ValueError("At least one field must be provided for update")

    if ctx:
        await ctx.report_progress(progress=70, total=100)
        ctx.debug("Sending API request")

    response: dict = await client.patch(f"cards/{card_id}", update_data)

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Card updated: {card_id}")

    card_name = response.get("title", "N/A")
    return {
        "content": [{"type": "text", "text": f"Card updated: {card_name}"}],
        "structured_content": response,
        "meta": {"operation": "update", "card_id": card_id},
    }


async def _delete_card(
    client: KaitenClient,
    card_id: int,
    ctx: Optional[Any],
) -> dict:
    """Delete a card from Kaiten."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    await client.delete(f"cards/{card_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Card deleted: {card_id}")

    return {
        "content": [{"type": "text", "text": f"Card {card_id} deleted"}],
        "structured_content": {"status": "deleted", "card_id": card_id},
        "meta": {"operation": "delete", "card_id": card_id},
    }


async def _list_cards(
    client: KaitenClient,
    board_id: Optional[int],
    board: Optional[str],
    space_id: Optional[int],
    column_id: Optional[int],
    condition: Optional[int],
    query: Optional[str],
    due_date_after: Optional[str],
    due_date_before: Optional[str],
    owner_id: Optional[int],
    owner_name: Optional[str],
    tag_ids: Optional[str],
    limit: Optional[int],
    skip: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """List cards from Kaiten with filtering."""
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

    resolved_owner_id = owner_id
    if owner_name is not None:
        if ctx:
            await ctx.report_progress(progress=30, total=100)
            ctx.debug(f"Resolving owner name: {owner_name}")
        found_owner_id = await find_user_by_name(client, owner_name)
        if found_owner_id is None:
            raise ValueError(f"User not found: {owner_name}")
        resolved_owner_id = found_owner_id
        if ctx:
            ctx.info(f"Owner '{owner_name}' resolved to ID: {found_owner_id}")

    if ctx:
        await ctx.report_progress(progress=40, total=100)
        ctx.debug("Building query parameters")

    params: Dict[str, Any] = {}
    if resolved_board_id is not None:
        params["board_id"] = resolved_board_id
    if space_id is not None:
        params["space_id"] = space_id
    if column_id is not None:
        params["column_id"] = column_id
    if condition is not None:
        params["condition"] = condition
    if query is not None:
        params["query"] = query
    if due_date_after is not None:
        params["due_date_after"] = due_date_after
    if due_date_before is not None:
        params["due_date_before"] = due_date_before
    if resolved_owner_id is not None:
        params["owner_id"] = resolved_owner_id
    if tag_ids is not None:
        tag_list = [int(tid.strip()) for tid in tag_ids.split(",") if tid.strip()]
        if tag_list:
            params["tag_ids"] = tag_list
    if limit is not None:
        params["limit"] = limit
    if skip is not None:
        params["offset"] = skip

    if ctx:
        await ctx.report_progress(progress=60, total=100)
        ctx.debug("Sending API request")

    endpoint = "cards"
    if params:
        query_parts = []
        for k, v in params.items():
            if isinstance(v, list):
                query_parts.append(f"{k}={','.join(map(str, v))}")
            else:
                query_parts.append(f"{k}={v}")
        endpoint = f"{endpoint}?{'&'.join(query_parts)}"

    response: Union[dict, List[dict]] = await client.get(endpoint)

    cards: List[dict]
    if isinstance(response, list):
        cards = response
    elif isinstance(response, dict) and "cards" in response:
        cards = response["cards"]
    elif isinstance(response, dict) and "data" in response:
        cards = response["data"]
    else:
        cards = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(cards)} cards")

    if not cards:
        return {
            "content": [{"type": "text", "text": "No cards found."}],
            "structured_content": [],
            "meta": {"operation": "list", "count": 0, "filters": params},
        }

    card_list_text = "\n".join(
        f"• {c.get('title', 'N/A')} (ID: {c.get('id', 'N/A')})" for c in cards[:20]
    )
    if len(cards) > 20:
        card_list_text += f"\n... and {len(cards) - 20} more cards"

    return {
        "content": [
            {"type": "text", "text": f"Found {len(cards)} cards:\n{card_list_text}"}
        ],
        "structured_content": cards,
        "meta": {"operation": "list", "count": len(cards), "filters": params},
    }


async def _search_cards(
    client: KaitenClient,
    query: str,
    board_id: Optional[int],
    board: Optional[str],
    space_id: Optional[int],
    limit: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """Search cards in Kaiten."""
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

    if ctx:
        await ctx.report_progress(progress=40, total=100)
        ctx.debug("Building query parameters")

    params: Dict[str, Any] = {"query": query}
    if resolved_board_id is not None:
        params["board_id"] = resolved_board_id
    if space_id is not None:
        params["space_id"] = space_id
    if limit is not None:
        params["limit"] = limit

    if ctx:
        await ctx.report_progress(progress=60, total=100)
        ctx.debug("Sending API request")

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    endpoint = f"cards?{query_string}"

    response: Union[dict, List[Dict[str, Any]]] = await client.get(endpoint)

    cards: List[Dict[str, Any]]
    if isinstance(response, list):
        cards = response
    elif isinstance(response, dict) and "cards" in response:
        cards = response["cards"]
    elif isinstance(response, dict) and "data" in response:
        cards = response["data"]
    else:
        cards = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Found {len(cards)} cards matching query")

    if not cards:
        return {
            "content": [
                {"type": "text", "text": f"No cards found for query: '{query}'"}
            ],
            "structured_content": [],
            "meta": {"operation": "search", "query": query, "count": 0},
        }

    card_list_text = "\n".join(
        f"• {c.get('title', 'N/A')} (ID: {c.get('id', 'N/A')})" for c in cards[:20]
    )
    if len(cards) > 20:
        card_list_text += f"\n... and {len(cards) - 20} more cards"

    return {
        "content": [
            {
                "type": "text",
                "text": f"Found {len(cards)} cards for '{query}':\n{card_list_text}",
            }
        ],
        "structured_content": cards,
        "meta": {"operation": "search", "query": query, "count": len(cards)},
    }


@mcp.tool(
    name="manage_cards",
    description=(
        "Unified tool for card operations. "
        "Actions: create, get, update, delete, list, search. "
        "IMPORTANT: Pass 'board' parameter with board NAME - ID is resolved automatically. "
        "No need to call list first. "
        "Example: manage_cards(action='create', board='Sprint 5', title='New Task')"
    ),
)
@log_method_call(log_input=True, log_output=True, log_errors=True)
async def manage_cards(
    action: Literal["create", "get", "update", "delete", "list", "search"] = Field(
        ..., description="Action to perform"
    ),
    card_id: Optional[int] = Field(
        None, description="Card ID (required for get/update/delete)", gt=0
    ),
    title: Optional[str] = Field(None, description="Card title (required for create)"),
    board_id: Optional[int] = Field(
        None, description="Board ID (required for create)", gt=0
    ),
    board: Optional[str] = Field(
        None,
        description="Board name - automatically resolved to ID, preferred over board_id",
    ),
    asap: Optional[bool] = Field(
        None,
        description="Whether the card is urgent; omitted values are unchanged on update",
    ),
    due_date: Optional[str] = Field(None, description="Due date in YYYY-MM-DD format"),
    description: Optional[str] = Field(None, description="Card description"),
    space_id: Optional[int] = Field(None, description="Space ID for filtering", gt=0),
    column_id: Optional[int] = Field(None, description="Column ID for filtering", gt=0),
    condition: Optional[int] = Field(1, description="1=active, 2=archived", ge=1, le=2),
    query: Optional[str] = Field(None, description="Text search query"),
    due_date_after: Optional[str] = Field(
        None, description="Filter by due date after (ISO 8601)"
    ),
    due_date_before: Optional[str] = Field(
        None, description="Filter by due date before (ISO 8601)"
    ),
    owner_id: Optional[int] = Field(None, description="Filter by owner ID", gt=0),
    owner_name: Optional[str] = Field(
        None,
        description="Filter by owner name - automatically resolved to ID, preferred over owner_id",
    ),
    tag_ids: Optional[str] = Field(None, description="Comma-separated tag IDs"),
    limit: Optional[int] = Field(
        50, description="Max results (default 50)", ge=1, le=100
    ),
    skip: Optional[int] = Field(0, description="Pagination offset", ge=0),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified card management tool.

    Args:
        action: Operation to perform (create/get/update/delete/list/search).
        card_id: Card identifier (required for get/update/delete).
        title: Card title (required for create).
        board_id: Board identifier (required for create).
        board: Board name (alternative to board_id).
        asap: Whether card is urgent.
        due_date: Due date in YYYY-MM-DD format.
        description: Card description.
        space_id: Space ID for filtering.
        column_id: Column ID for filtering.
        condition: Card condition (1=active, 2=archived).
        query: Text search query (required for search).
        due_date_after: Filter cards after this date.
        due_date_before: Filter cards before this date.
        owner_id: Filter by owner ID.
        owner_name: Filter by owner name (alternative to owner_id, auto-resolved).
        tag_ids: Comma-separated tag IDs for filtering.
        limit: Maximum results to return.
        skip: Pagination offset.
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        ValidationError: If card data is invalid.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"manage_cards: action={action}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        logger.info(
            "Starting manage_cards operation",
            extra={
                "method_name": "manage_cards",
                "input_params": {
                    "action": action,
                    "card_id": card_id,
                    "has_title": title is not None,
                    "has_board": board is not None,
                    "board_id": board_id,
                },
            },
        )
        if action == "create":
            if title is None:
                raise ValueError("title is required for create action")
            # Resolve board name to board_id if needed
            resolved_board_id = await _resolve_board_id(client, board_id, board, ctx)
            return await _create_card(
                client,
                title,
                resolved_board_id,
                asap if asap is not None else False,
                due_date,
                description,
                ctx,
            )

        if action == "get":
            if card_id is None:
                raise ValueError("card_id is required for get action")
            return await _get_card(client, card_id, ctx)

        if action == "update":
            if card_id is None:
                raise ValueError("card_id is required for update action")
            update_board: Optional[Union[int, str]] = (
                board if board is not None else board_id
            )
            return await _update_card(
                client,
                card_id,
                title,
                update_board,
                asap,
                due_date,
                description,
                ctx,
            )

        if action == "delete":
            if card_id is None:
                raise ValueError("card_id is required for delete action")
            return await _delete_card(client, card_id, ctx)

        if action == "list":
            return await _list_cards(
                client,
                board_id,
                board,
                space_id,
                column_id,
                condition,
                query,
                due_date_after,
                due_date_before,
                owner_id,
                owner_name,
                tag_ids,
                limit,
                skip,
                ctx,
            )

        if action == "search":
            if query is None:
                raise ValueError("query is required for search action")
            return await _search_cards(
                client, query, board_id, board, space_id, limit, ctx
            )

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_cards failed: {e}"
        logger.error(
            error_msg,
            extra={
                "method_name": "manage_cards",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "action": action,
            },
            exc_info=True,
        )
        if ctx:
            ctx.error(error_msg)
        raise

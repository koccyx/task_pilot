"""Unified tool for space operations in Kaiten."""

from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from chat_bot.mcp_server.models.space import Space
from pydantic import Field, ValidationError


async def _list_spaces(
    client: KaitenClient,
    ctx: Optional[Any],
) -> dict:
    """List all spaces."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: Union[dict, List[Dict[str, Any]]] = await client.get("spaces")

    spaces: List[Dict[str, Any]]
    if isinstance(response, list):
        spaces = response
    elif isinstance(response, dict) and "spaces" in response:
        spaces = response["spaces"]
    else:
        spaces = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(spaces)} spaces")

    spaces_text = "\n".join(
        f"• {s.get('title', s.get('name', 'N/A'))} (ID: {s.get('id', 'N/A')})"
        for s in spaces
    )

    return {
        "content": [
            {"type": "text", "text": f"Found {len(spaces)} spaces:\n{spaces_text}"}
        ],
        "structured_content": spaces,
        "meta": {"operation": "list", "count": len(spaces)},
    }


async def _create_space(
    client: KaitenClient,
    title: str,
    ctx: Optional[Any],
) -> dict:
    """Create a new space."""
    if ctx:
        await ctx.report_progress(progress=25, total=100)
        ctx.debug("Validating space data")

    try:
        space_data = Space(title=title)
    except ValidationError as e:
        raise ValueError(f"Space validation failed: {e}") from e

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Preparing API request")

    space_dict = space_data.model_dump(exclude={"id"}, exclude_none=True)

    if ctx:
        await ctx.report_progress(progress=75, total=100)
        ctx.info("Sending API request")

    response: dict = await client.post("spaces", space_dict)
    space_id = response.get("id")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Space created: {space_id}")

    return {
        "content": [
            {"type": "text", "text": f"Space '{title}' created with ID: {space_id}"}
        ],
        "structured_content": response,
        "meta": {"operation": "create", "space_id": space_id},
    }


async def _update_space(
    client: KaitenClient,
    space_id: int,
    title: Optional[str],
    ctx: Optional[Any],
) -> dict:
    """Update a space."""
    update_data: Dict[str, Any] = {}

    if title is not None:
        update_data["title"] = title
        if ctx:
            ctx.debug(f"Updating space title: {title}")

    if not update_data:
        raise ValueError("At least one field must be provided for update")

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: dict = await client.patch(f"spaces/{space_id}", update_data)

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Space updated: {space_id}")

    space_name = response.get("title", response.get("name", "N/A"))
    return {
        "content": [
            {"type": "text", "text": f"Space updated: {space_name} (ID: {space_id})"}
        ],
        "structured_content": response,
        "meta": {"operation": "update", "space_id": space_id},
    }


async def _delete_space(
    client: KaitenClient,
    space_id: int,
    ctx: Optional[Any],
) -> dict:
    """Delete a space."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    await client.delete(f"spaces/{space_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Space deleted: {space_id}")

    return {
        "content": [{"type": "text", "text": f"Space {space_id} deleted"}],
        "structured_content": {"status": "deleted", "space_id": space_id},
        "meta": {"operation": "delete", "space_id": space_id},
    }


@mcp.tool(
    name="manage_spaces",
    description=(
        "Unified tool for space operations. "
        "Actions: list, create, update, delete. "
        "Use 'list' to see all spaces, 'create' to add a new space, "
        "'update' to modify a space, 'delete' to remove a space."
    ),
)
async def manage_spaces(
    action: Literal["list", "create", "update", "delete"] = Field(
        ..., description="Action to perform"
    ),
    space_id: Optional[int] = Field(
        None, description="Space ID (required for update/delete)", gt=0
    ),
    title: Optional[str] = Field(
        None,
        description="Space title (required for create, optional for update)",
        max_length=256,
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified space management tool.

    Args:
        action: Operation to perform (list/create/update/delete).
        space_id: Space identifier (required for update/delete).
        title: Space title (required for create, optional for update).
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"manage_spaces: action={action}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        if action == "list":
            return await _list_spaces(client, ctx)

        if action == "create":
            if title is None:
                raise ValueError("title is required for create action")
            return await _create_space(client, title, ctx)

        if action == "update":
            if space_id is None:
                raise ValueError("space_id is required for update action")
            return await _update_space(client, space_id, title, ctx)

        if action == "delete":
            if space_id is None:
                raise ValueError("space_id is required for delete action")
            return await _delete_space(client, space_id, ctx)

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_spaces failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

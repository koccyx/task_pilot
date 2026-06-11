"""Unified tool for tag operations in Kaiten."""

from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from chat_bot.mcp_server.models.tag import Tag
from pydantic import Field, ValidationError

from .helpers import find_tag_by_name


async def _list_tags(
    client: KaitenClient,
    card_id: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """List tags, optionally filtered by card."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    endpoint = "tags"
    if card_id:
        endpoint = f"tags?card_id={card_id}"

    response: Union[dict, List[Dict[str, Any]]] = await client.get(endpoint)

    tags: List[Dict[str, Any]]
    if isinstance(response, list):
        tags = response
    elif isinstance(response, dict) and "tags" in response:
        tags = response["tags"]
    else:
        tags = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(tags)} tags")

    tags_text = "\n".join(
        f"• {t.get('name', 'N/A')} (ID: {t.get('id', 'N/A')})" for t in tags
    )

    return {
        "content": [{"type": "text", "text": f"Found {len(tags)} tags:\n{tags_text}"}],
        "structured_content": tags,
        "meta": {"operation": "list", "card_id": card_id, "count": len(tags)},
    }


async def _create_tag(
    client: KaitenClient,
    name: str,
    card_id: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """Create a tag and optionally attach to a card."""
    if ctx:
        await ctx.report_progress(progress=25, total=100)
        ctx.debug("Validating tag data")

    try:
        tag_data = Tag(name=name)
    except ValidationError as e:
        raise ValueError(f"Tag validation failed: {e}") from e

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Preparing API request")

    tag_dict = tag_data.model_dump(exclude={"id"}, exclude_none=True)

    if ctx:
        await ctx.report_progress(progress=75, total=100)
        ctx.info("Sending API request")

    if card_id:
        response: dict = await client.post(f"cards/{card_id}/tags", tag_dict)
    else:
        response = await client.post("tags", tag_dict)

    tag_id = response.get("id")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Tag created: {tag_id}")

    text = f"Tag '{name}' created with ID: {tag_id}"
    if card_id:
        text += f" and attached to card {card_id}"

    return {
        "content": [{"type": "text", "text": text}],
        "structured_content": response,
        "meta": {"operation": "create", "tag_id": tag_id, "card_id": card_id},
    }


async def _remove_tag(
    client: KaitenClient,
    tag_id: int,
    card_id: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """Remove a tag (optionally from a specific card)."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    if card_id:
        endpoint = f"cards/{card_id}/tags/{tag_id}"
    else:
        endpoint = f"tags/{tag_id}"

    await client.delete(endpoint)

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Tag removed: {tag_id}")

    text = f"Tag {tag_id} removed"
    if card_id:
        text += f" from card {card_id}"

    return {
        "content": [{"type": "text", "text": text}],
        "structured_content": {"status": "deleted", "tag_id": tag_id, "card_id": card_id},
        "meta": {"operation": "remove", "tag_id": tag_id, "card_id": card_id},
    }


@mcp.tool(
    name="manage_tags",
    description=(
        "Unified tool for tag operations. "
        "Actions: list, create, remove. "
        "Use 'list' to see tags, 'create' to add a new tag, 'remove' to delete a tag."
    ),
)
async def manage_tags(
    action: Literal["list", "create", "remove"] = Field(
        ..., description="Action to perform"
    ),
    tag_id: Optional[int] = Field(
        None, description="Tag ID (required for remove)", gt=0
    ),
    tag: Optional[str] = Field(
        None,
        description="Tag name - automatically resolved to ID, preferred over tag_id (for remove)",
    ),
    card_id: Optional[int] = Field(
        None, description="Card ID for filtering or attaching tag", gt=0
    ),
    name: Optional[str] = Field(None, description="Tag name (required for create)"),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified tag management tool.

    Args:
        action: Operation to perform (list/create/remove).
        tag_id: Tag identifier (required for remove).
        tag: Tag name (alternative to tag_id, for remove).
        card_id: Card ID for filtering tags, attaching new tag, or removing tag from card.
        name: Tag name (required for create).
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"manage_tags: action={action}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        if action == "list":
            return await _list_tags(client, card_id, ctx)

        if action == "create":
            if name is None:
                raise ValueError("name is required for create action")
            return await _create_tag(client, name, card_id, ctx)

        if action == "remove":
            resolved_tag_id = tag_id
            if tag is not None:
                if ctx:
                    await ctx.report_progress(progress=20, total=100)
                    ctx.debug(f"Resolving tag name: {tag}")
                found_tag_id = await find_tag_by_name(client, tag, card_id=card_id)
                if found_tag_id is None:
                    raise ValueError(f"Tag not found: {tag}")
                resolved_tag_id = found_tag_id
                if ctx:
                    ctx.info(f"Tag '{tag}' resolved to ID: {found_tag_id}")

            if resolved_tag_id is None:
                raise ValueError("Either tag_id or tag name must be provided")
            return await _remove_tag(client, resolved_tag_id, card_id, ctx)

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_tags failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

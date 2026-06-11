"""Unified tool for comment operations in Kaiten."""

from typing import Any, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from chat_bot.mcp_server.models.comment import Comment
from pydantic import Field, ValidationError


async def _add_comment(
    client: KaitenClient,
    card_id: int,
    text: str,
    attachments: Optional[List[Any]],
    ctx: Optional[Any],
) -> dict:
    """Add a comment to a card."""
    if ctx:
        await ctx.report_progress(progress=25, total=100)
        ctx.debug("Validating comment data")

    try:
        comment = Comment(card_id=card_id, text=text, attachments=attachments)
    except ValidationError as e:
        error_msg = f"Comment validation failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Preparing comment data")

    comment_data = comment.model_dump(
        exclude={"id", "card_id", "author_id", "created_at", "updated_at"},
        exclude_none=True,
    )

    if ctx:
        await ctx.report_progress(progress=75, total=100)
        ctx.info("Sending API request")

    response: dict = await client.post(f"cards/{card_id}/comments", comment_data)
    comment_id = response.get("id")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Comment created: {comment_id}")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Comment added to card {card_id} (ID: {comment_id})",
            }
        ],
        "structured_content": response,
        "meta": {"operation": "add", "card_id": card_id, "comment_id": comment_id},
    }


async def _show_comments(
    client: KaitenClient,
    card_id: int,
    ctx: Optional[Any],
) -> dict:
    """Get all comments for a card."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: Union[dict, List[dict]] = await client.get(f"cards/{card_id}/comments")

    comments: List[dict]
    if isinstance(response, list):
        comments = response
    elif isinstance(response, dict) and "comments" in response:
        comments = response["comments"]
    elif isinstance(response, dict) and "data" in response:
        comments = response["data"]
    else:
        comments = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(comments)} comments for card {card_id}")

    if not comments:
        return {
            "content": [
                {"type": "text", "text": f"No comments found for card {card_id}."}
            ],
            "structured_content": [],
            "meta": {"operation": "show", "card_id": card_id, "count": 0},
        }

    parts: List[str] = [f"💬 Comments for card {card_id}:\n"]
    for idx, comment in enumerate(comments, 1):
        comment_id = comment.get("id", "N/A")
        comment_text = comment.get("text", "N/A")
        author = comment.get("author", {})
        author_name = (
            author.get("name")
            or author.get("full_name")
            or author.get("username")
            or "Unknown"
        )
        created_at = comment.get("created_at", comment.get("created", "N/A"))
        display_text = (
            comment_text[:200] + "..." if len(comment_text) > 200 else comment_text
        )
        parts.append(
            f"{idx}. [{comment_id}] {author_name} ({created_at}):\n   {display_text}\n"
        )

    return {
        "content": [{"type": "text", "text": "\n".join(parts)}],
        "structured_content": comments,
        "meta": {"operation": "show", "card_id": card_id, "count": len(comments)},
    }


async def _update_comment(
    client: KaitenClient,
    card_id: int,
    comment_id: int,
    text: str,
    ctx: Optional[Any],
) -> dict:
    """Update an existing comment."""
    if not text or len(text.strip()) == 0:
        raise ValueError("Comment text cannot be empty")

    if len(text) > 4096:
        raise ValueError("Comment text cannot exceed 4096 characters")

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Preparing update data")

    update_data = {"text": text}

    if ctx:
        await ctx.report_progress(progress=75, total=100)
        ctx.info("Sending API request")

    response: dict = await client.patch(
        f"cards/{card_id}/comments/{comment_id}", update_data
    )

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Comment updated: {comment_id}")

    return {
        "content": [
            {"type": "text", "text": f"Comment {comment_id} updated on card {card_id}"}
        ],
        "structured_content": response,
        "meta": {"operation": "update", "card_id": card_id, "comment_id": comment_id},
    }


async def _delete_comment(
    client: KaitenClient,
    card_id: int,
    comment_id: int,
    ctx: Optional[Any],
) -> dict:
    """Delete a comment from a card."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    await client.delete(f"cards/{card_id}/comments/{comment_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Comment deleted: {comment_id}")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Comment {comment_id} deleted from card {card_id}",
            }
        ],
        "structured_content": {"success": True},
        "meta": {"operation": "delete", "card_id": card_id, "comment_id": comment_id},
    }


@mcp.tool(
    name="manage_comments",
    description=(
        "Unified tool for comment operations. "
        "Actions: add, show, update, delete. "
        "Use 'add' to create a comment, 'show' to list comments, "
        "'update' to modify, 'delete' to remove."
    ),
)
async def manage_comments(
    action: Literal["add", "show", "update", "delete"] = Field(
        ..., description="Action to perform"
    ),
    card_id: int = Field(..., description="Card ID", gt=0),
    comment_id: Optional[int] = Field(
        None, description="Comment ID (required for update/delete)", gt=0
    ),
    text: Optional[str] = Field(
        None, description="Comment text (required for add/update)", max_length=4096
    ),
    attachments: Optional[List[Any]] = Field(
        None, description="Optional attachments for add action"
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified comment management tool.

    Args:
        action: Operation to perform (add/show/update/delete).
        card_id: Identifier of the card.
        comment_id: Comment identifier (required for update/delete).
        text: Comment text (required for add/update).
        attachments: Optional attachments for add action.
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        ValidationError: If comment data is invalid.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"manage_comments: action={action}, card_id={card_id}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        if action == "add":
            if text is None:
                raise ValueError("text is required for add action")
            return await _add_comment(client, card_id, text, attachments, ctx)

        if action == "show":
            return await _show_comments(client, card_id, ctx)

        if action == "update":
            if comment_id is None:
                raise ValueError("comment_id is required for update action")
            if text is None:
                raise ValueError("text is required for update action")
            return await _update_comment(client, card_id, comment_id, text, ctx)

        if action == "delete":
            if comment_id is None:
                raise ValueError("comment_id is required for delete action")
            return await _delete_comment(client, card_id, comment_id, ctx)

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_comments failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

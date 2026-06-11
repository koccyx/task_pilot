"""Unified tool for time log operations in Kaiten."""

from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from chat_bot.mcp_server.models.time_log import TimeLog
from pydantic import Field, ValidationError


async def _list_time_logs(
    client: KaitenClient,
    card_id: int,
    for_date: Optional[str],
    personal: Optional[bool],
    ctx: Optional[Any],
) -> dict:
    """List time logs for a card."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    params: List[str] = []
    if for_date:
        params.append(f"for_date={for_date}")
    if personal is not None:
        params.append(f"personal={str(personal).lower()}")

    endpoint = f"cards/{card_id}/time_logs"
    if params:
        endpoint += "?" + "&".join(params)

    response: Union[dict, List[Dict[str, Any]]] = await client.get(endpoint)

    time_logs: List[Dict[str, Any]]
    if isinstance(response, list):
        time_logs = response
    elif isinstance(response, dict) and "time_logs" in response:
        time_logs = response["time_logs"]
    else:
        time_logs = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(time_logs)} time logs")

    total_minutes = sum(log.get("time_spent", 0) for log in time_logs)
    hours = total_minutes // 60
    minutes = total_minutes % 60

    logs_text = "\n".join(
        f"• {log.get('time_spent', 0)} min on {log.get('for_date', 'N/A')} - {log.get('comment', 'No comment')}"
        for log in time_logs
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Found {len(time_logs)} time logs (total: {hours}h {minutes}m):\n{logs_text}",
            }
        ],
        "structured_content": time_logs,
        "meta": {
            "operation": "list",
            "card_id": card_id,
            "count": len(time_logs),
            "total_minutes": total_minutes,
        },
    }


async def _log_time(
    client: KaitenClient,
    card_id: int,
    time_spent: int,
    for_date: str,
    role_id: int,
    comment: Optional[str],
    ctx: Optional[Any],
) -> dict:
    """Log time on a card."""
    if ctx:
        await ctx.report_progress(progress=25, total=100)
        ctx.debug("Validating time log data")

    try:
        time_log_data = TimeLog(
            card_id=card_id,
            time_spent=time_spent,
            for_date=for_date,
            role_id=role_id,
            comment=comment,
        )
    except ValidationError as e:
        raise ValueError(f"Time log validation failed: {e}") from e

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Preparing API request")

    time_log_dict = time_log_data.model_dump(
        exclude={"id", "card_id"}, exclude_none=True
    )

    if ctx:
        await ctx.report_progress(progress=75, total=100)
        ctx.info("Sending API request")

    response: dict = await client.post(f"cards/{card_id}/time_logs", time_log_dict)
    log_id = response.get("id")
    hours = time_spent // 60
    minutes = time_spent % 60

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Time log created: {log_id}")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Time logged: {hours}h {minutes}m on {for_date} (Log ID: {log_id})",
            }
        ],
        "structured_content": response,
        "meta": {
            "operation": "log",
            "log_id": log_id,
            "card_id": card_id,
            "time_spent": time_spent,
        },
    }


async def _update_time_log(
    client: KaitenClient,
    card_id: int,
    time_log_id: int,
    time_spent: Optional[int],
    for_date: Optional[str],
    role_id: Optional[int],
    comment: Optional[str],
    ctx: Optional[Any],
) -> dict:
    """Update a time log."""
    update_data: Dict[str, Any] = {}

    if time_spent is not None:
        update_data["time_spent"] = time_spent
        if ctx:
            ctx.debug(f"Updating time_spent: {time_spent}")

    if for_date is not None:
        update_data["for_date"] = for_date
        if ctx:
            ctx.debug(f"Updating for_date: {for_date}")

    if role_id is not None:
        update_data["role_id"] = role_id
        if ctx:
            ctx.debug(f"Updating role_id: {role_id}")

    if comment is not None:
        update_data["comment"] = comment
        if ctx:
            ctx.debug(f"Updating comment: {comment}")

    if not update_data:
        raise ValueError("At least one field must be provided for update")

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: dict = await client.patch(
        f"cards/{card_id}/time-logs/{time_log_id}", update_data
    )

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Time log updated: {time_log_id}")

    updated_time = update_data.get("time_spent", response.get("time_spent", 0))
    hours = updated_time // 60
    minutes = updated_time % 60
    updated_date = update_data.get("for_date", response.get("for_date", "N/A"))

    return {
        "content": [
            {
                "type": "text",
                "text": f"Time log updated: {hours}h {minutes}m on {updated_date} (Log ID: {time_log_id})",
            }
        ],
        "structured_content": response,
        "meta": {
            "operation": "update",
            "log_id": time_log_id,
            "card_id": card_id,
        },
    }


async def _delete_time_log(
    client: KaitenClient,
    card_id: int,
    time_log_id: int,
    ctx: Optional[Any],
) -> dict:
    """Delete a time log."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    await client.delete(f"cards/{card_id}/time-logs/{time_log_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Time log deleted: {time_log_id}")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Time log {time_log_id} deleted from card {card_id}",
            }
        ],
        "structured_content": {
            "status": "deleted",
            "log_id": time_log_id,
            "card_id": card_id,
        },
        "meta": {"operation": "delete", "log_id": time_log_id, "card_id": card_id},
    }


@mcp.tool(
    name="manage_time_logs",
    description=(
        "Unified tool for time log operations. "
        "Actions: list, log, update, delete. "
        "Use 'list' to see time logs for a card, 'log' to record time spent, "
        "'update' to modify a time log, 'delete' to remove a time log."
    ),
)
async def manage_time_logs(
    action: Literal["list", "log", "update", "delete"] = Field(
        ..., description="Action to perform"
    ),
    card_id: int = Field(..., description="Card ID", gt=0),
    time_log_id: Optional[int] = Field(
        None, description="Time log ID (required for update/delete)", gt=0
    ),
    time_spent: Optional[int] = Field(
        None,
        description="Time spent in minutes (required for log, optional for update)",
        gt=0,
    ),
    for_date: Optional[str] = Field(
        None, description="Date YYYY-MM-DD (required for log, optional for list/update)"
    ),
    role_id: Optional[int] = Field(
        None, description="Role ID (required for log, optional for update)", gt=0
    ),
    comment: Optional[str] = Field(None, description="Comment (for log/update)"),
    personal: Optional[bool] = Field(
        None, description="Filter by current user only (for list)"
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified time log management tool.

    Args:
        action: Operation to perform (list/log/update/delete).
        card_id: Card identifier.
        time_log_id: Time log identifier (required for update/delete).
        time_spent: Time spent in minutes (required for log, optional for update).
        for_date: Date for log/update action or filter for list.
        role_id: Role identifier (required for log, optional for update).
        comment: Comment (for log/update).
        personal: Filter by current user for list action.
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(f"manage_time_logs: action={action}, card_id={card_id}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        if action == "list":
            return await _list_time_logs(client, card_id, for_date, personal, ctx)

        if action == "log":
            if time_spent is None:
                raise ValueError("time_spent is required for log action")
            if for_date is None:
                raise ValueError("for_date is required for log action")
            if role_id is None:
                raise ValueError("role_id is required for log action")
            return await _log_time(
                client, card_id, time_spent, for_date, role_id, comment, ctx
            )

        if action == "update":
            if time_log_id is None:
                raise ValueError("time_log_id is required for update action")
            return await _update_time_log(
                client,
                card_id,
                time_log_id,
                time_spent,
                for_date,
                role_id,
                comment,
                ctx,
            )

        if action == "delete":
            if time_log_id is None:
                raise ValueError("time_log_id is required for delete action")
            return await _delete_time_log(client, card_id, time_log_id, ctx)

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_time_logs failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

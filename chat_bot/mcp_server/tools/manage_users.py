"""Unified tool for user operations in Kaiten."""

import logging
from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from pydantic import Field

from .helpers import find_space_by_name

logger = logging.getLogger(__name__)


async def _list_users(
    client: KaitenClient,
    offset: Optional[int],
    limit: Optional[int],
    ctx: Optional[Any],
) -> dict:
    """List all users in the company."""
    logger.info(
        f"[_list_users] Called with offset={offset}, limit={limit}"
    )
    
    if ctx:
        await ctx.report_progress(progress=30, total=100)
        ctx.debug("Building query parameters")

    params: Dict[str, Any] = {}
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit

    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    endpoint = "users"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        endpoint = f"{endpoint}?{query_string}"

    logger.info(f"[_list_users] Making API request to endpoint: {endpoint}")
    logger.debug(f"[_list_users] Request params: {params}")

    response = await client.get(endpoint)

    logger.info(f"[_list_users] Received API response, type: {type(response)}")
    logger.debug(f"[_list_users] Raw response (first 500 chars): {str(response)[:500]}")

    users: List[dict]
    if isinstance(response, list):
        users = response
        logger.debug(f"[_list_users] Response is a list with {len(users)} items")
    elif isinstance(response, dict) and "users" in response:
        users = response["users"]
        logger.debug(f"[_list_users] Response is a dict with 'users' key, found {len(users)} users")
    elif isinstance(response, dict) and "data" in response:
        users = response["data"]
        logger.debug(f"[_list_users] Response is a dict with 'data' key, found {len(users)} users")
    else:
        users = [response] if response else []
        logger.warning(f"[_list_users] Unexpected response format, extracted {len(users)} users")
        logger.debug(f"[_list_users] Response keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")

    logger.info(f"[_list_users] Total users extracted: {len(users)}")
    if users:
        logger.debug(f"[_list_users] First user sample: {users[0]}")
        logger.debug(f"[_list_users] User IDs: {[u.get('id', 'N/A') for u in users[:10]]}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(users)} users")

    if not users:
        return {
            "content": [{"type": "text", "text": "No users found."}],
            "structured_content": [],
            "meta": {"operation": "list", "count": 0, "offset": offset, "limit": limit},
        }

    user_list_text = "\n".join(
        f"• ID: {u.get('id', 'N/A')} | full_name: {u.get('full_name', u.get('name', 'N/A'))} | "
        f"username: {u.get('username', 'N/A')} | email: {u.get('email', 'N/A')}"
        for u in users[:20]
    )
    if len(users) > 20:
        user_list_text += f"\n... and {len(users) - 20} more users"

    return {
        "content": [
            {"type": "text", "text": f"Found {len(users)} users:\n{user_list_text}"}
        ],
        "structured_content": users,
        "meta": {
            "operation": "list",
            "count": len(users),
            "offset": offset,
            "limit": limit,
        },
    }


async def _space_members(
    client: KaitenClient,
    space_id: int,
    ctx: Optional[Any],
) -> dict:
    """Get members of a space."""
    if ctx:
        await ctx.report_progress(progress=60, total=100)
        ctx.debug("Sending API request")

    response: Union[dict, List[dict]] = await client.get(f"spaces/{space_id}/users")

    users: List[dict]
    if isinstance(response, list):
        users = response
    elif isinstance(response, dict) and "users" in response:
        users = response["users"]
    elif isinstance(response, dict) and "data" in response:
        users = response["data"]
    else:
        users = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(users)} space members")

    if not users:
        return {
            "content": [
                {"type": "text", "text": f"No members found in space {space_id}."}
            ],
            "structured_content": [],
            "meta": {"operation": "space_members", "space_id": space_id, "count": 0},
        }

    user_list_text = "\n".join(
        f"• {u.get('name', u.get('full_name', 'N/A'))} (ID: {u.get('id', 'N/A')}, Email: {u.get('email', 'N/A')})"
        for u in users
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Found {len(users)} members in space {space_id}:\n{user_list_text}",
            }
        ],
        "structured_content": users,
        "meta": {
            "operation": "space_members",
            "space_id": space_id,
            "count": len(users),
        },
    }


@mcp.tool(
    name="manage_users",
    description=(
        "Unified tool for user operations. "
        "Actions: list, space_members. "
        "IMPORTANT: For space_members, pass 'space' with space NAME - ID is resolved automatically. "
        "No need to call list first. "
        "Example: manage_users(action='space_members', space='Marketing')"
    ),
)
async def manage_users(
    action: Literal["list", "space_members"] = Field(
        ..., description="Action to perform"
    ),
    space_id: Optional[int] = Field(
        None, description="Space ID (required for space_members)", gt=0
    ),
    space: Optional[str] = Field(
        None,
        description="Space name - automatically resolved to ID, preferred over space_id",
    ),
    offset: Optional[int] = Field(0, description="Pagination offset (for list)", ge=0),
    limit: Optional[int] = Field(
        50, description="Max results (for list)", ge=1, le=100
    ),
    ctx: Optional[Any] = None,
) -> dict:
    """Unified user management tool.

    Args:
        action: Operation to perform (list/space_members).
        space_id: Space identifier for space_members action.
        space: Space name (alternative to space_id) for space_members action.
        offset: Pagination offset for list action.
        limit: Maximum results for list action.
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        Exception: If API request fails.
    """
    logger.info(
        f"[manage_users] Called with action={action}, offset={offset}, limit={limit}, "
        f"space_id={space_id}, space={space}"
    )

    if ctx:
        ctx.info(f"manage_users: action={action}")
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        if action == "list":
            logger.info(f"[manage_users] Calling _list_users with offset={offset}, limit={limit}")
            result = await _list_users(client, offset, limit, ctx)
            logger.info(f"[manage_users] _list_users returned {result.get('meta', {}).get('count', 0)} users")
            logger.debug(f"[manage_users] Result meta: {result.get('meta', {})}")
            return result

        if action == "space_members":
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
                raise ValueError(
                    "Either space_id or space name must be provided for space_members"
                )
            return await _space_members(client, resolved_space_id, ctx)

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_users failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

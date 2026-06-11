"""Unified tool for member operations in Kaiten."""

from typing import Any, Dict, List, Literal, Optional, Union

from chat_bot.mcp_server.client.kaiten_client import KaitenClient, get_kaiten_client
from chat_bot.mcp_server.mcp_instance import mcp
from pydantic import Field

from .helpers import find_space_by_name, find_user_by_name


async def _resolve_user_id(
    client: KaitenClient,
    user_id: Optional[int],
    user_name: Optional[str],
    ctx: Optional[Any] = None,
) -> int:
    """Resolve user_id from user_name if needed.

    This is a convenience wrapper that combines validation and name resolution.
    Use this in MCP tools that accept either user_id or user_name.

    Args:
        client: HTTP client instance.
        user_id: Direct user ID (used if provided).
        user_name: User name to resolve (used if user_id is None).
        ctx: Optional MCP context for logging and progress.

    Returns:
        Resolved user ID.

    Raises:
        ValueError: If neither user_id nor user_name is provided, or user not found.
    """
    resolved_user_id = user_id
    if user_name is not None:
        if ctx:
            await ctx.report_progress(progress=20, total=100)
            ctx.debug(f"Resolving user name: {user_name}")
        found_id = await find_user_by_name(client, user_name)
        if found_id is None:
            raise ValueError(f"User not found: {user_name}")
        resolved_user_id = found_id
        if ctx:
            ctx.info(f"User '{user_name}' resolved to ID: {found_id}")

    if resolved_user_id is None:
        raise ValueError("Either user_id or user_name must be provided")
    return resolved_user_id


async def _resolve_space_id(
    client: KaitenClient,
    space_id: Optional[int],
    space_name: Optional[str],
    ctx: Optional[Any] = None,
) -> int:
    """Resolve space_id from space_name if needed.

    This is a convenience wrapper that combines validation and name resolution.
    Use this in MCP tools that accept either space_id or space (name).

    Args:
        client: HTTP client instance.
        space_id: Direct space ID (used if provided).
        space_name: Space name to resolve (used if space_id is None).
        ctx: Optional MCP context for logging and progress.

    Returns:
        Resolved space ID.

    Raises:
        ValueError: If neither space_id nor space_name is provided, or space not found.
    """
    resolved_space_id = space_id
    if space_name is not None:
        if ctx:
            await ctx.report_progress(progress=15, total=100)
            ctx.debug(f"Resolving space name: {space_name}")
        found_id = await find_space_by_name(client, space_name)
        if found_id is None:
            raise ValueError(f"Space not found: {space_name}")
        resolved_space_id = found_id
        if ctx:
            ctx.info(f"Space '{space_name}' resolved to ID: {found_id}")

    if resolved_space_id is None:
        raise ValueError("Either space_id or space must be provided")
    return resolved_space_id


async def _add_member(
    client: KaitenClient,
    card_id: int,
    user_id: int,
    user_name: Optional[str],
    ctx: Optional[Any],
) -> Dict[str, Any]:
    """Add a user as member to a card."""
    if ctx:
        await ctx.report_progress(progress=70, total=100)
        ctx.debug("Sending API request")

    member_data: Dict[str, int] = {"user_id": user_id}
    response: Dict[str, Any] = await client.post(
        f"cards/{card_id}/members", member_data
    )

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Member added to card: {card_id}")

    user_display = user_name or f"user ID {user_id}"
    return {
        "content": [
            {
                "type": "text",
                "text": f"User '{user_display}' (ID: {user_id}) added to card {card_id}",
            }
        ],
        "structured_content": response,
        "meta": {"operation": "add", "card_id": card_id, "user_id": user_id},
    }


async def _remove_member(
    client: KaitenClient,
    card_id: int,
    user_id: int,
    user_name: Optional[str],
    ctx: Optional[Any],
) -> Dict[str, Any]:
    """Remove a user from card members."""
    if ctx:
        await ctx.report_progress(progress=70, total=100)
        ctx.debug("Sending API request")

    await client.delete(f"cards/{card_id}/members/{user_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Member removed from card: {card_id}")

    user_display = user_name or f"user ID {user_id}"
    return {
        "content": [
            {
                "type": "text",
                "text": f"User '{user_display}' (ID: {user_id}) removed from card {card_id}",
            }
        ],
        "structured_content": {"success": True},
        "meta": {"operation": "remove", "card_id": card_id, "user_id": user_id},
    }


async def _list_members(
    client: KaitenClient,
    card_id: int,
    ctx: Optional[Any],
) -> Dict[str, Any]:
    """Get all members of a card."""
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Sending API request")

    response: Union[Dict[str, Any], List[Dict[str, Any]]] = await client.get(
        f"cards/{card_id}/members"
    )

    members: List[Dict[str, Any]]
    if isinstance(response, list):
        members = response
    elif isinstance(response, dict) and "members" in response:
        members = response["members"]
    elif isinstance(response, dict) and "data" in response:
        members = response["data"]
    else:
        members = [response] if response else []

    card_info: Dict[str, Any] = await client.get(f"cards/{card_id}")
    owner_id = card_info.get("owner_id")
    owner: Optional[Dict[str, Any]] = None
    if owner_id:
        try:
            owner = await client.get(f"users/{owner_id}")
        except Exception:
            owner = {"id": owner_id, "name": f"User {owner_id}"}

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(members)} members")

    parts: List[str] = []
    if owner:
        owner_name = owner.get("name", owner.get("full_name", "N/A"))
        parts.append(f"👤 Responsible: {owner_name} (ID: {owner.get('id', 'N/A')})")

    if members:
        if parts:
            parts.append("\n📋 Members:")
        else:
            parts.append("📋 Members:")
        for member in members:
            member_name = member.get("name", member.get("full_name", "N/A"))
            member_id = member.get("id", member.get("user_id", "N/A"))
            parts.append(f"  • {member_name} (ID: {member_id})")

    text = "\n".join(parts) if parts else "No members found for this card."

    return {
        "content": [{"type": "text", "text": f"Card {card_id} members:\n{text}"}],
        "structured_content": {"owner": owner, "members": members},
        "meta": {
            "operation": "list",
            "card_id": card_id,
            "owner_id": owner_id,
            "members_count": len(members),
        },
    }


async def _set_responsible(
    client: KaitenClient,
    card_id: int,
    owner_id: int,
    owner_name: Optional[str],
    ctx: Optional[Any],
) -> Dict[str, Any]:
    """Set responsible person for a card."""
    if ctx:
        await ctx.report_progress(progress=70, total=100)
        ctx.debug("Sending API request")

    update_data: Dict[str, int] = {"owner_id": owner_id}
    response: Dict[str, Any] = await client.patch(f"cards/{card_id}", update_data)

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Responsible set for card: {card_id}")

    card_name = response.get("title", "N/A")
    owner_display = owner_name or f"user ID {owner_id}"
    return {
        "content": [
            {
                "type": "text",
                "text": f"Responsible '{owner_display}' (ID: {owner_id}) set for card '{card_name}'",
            }
        ],
        "structured_content": response,
        "meta": {
            "operation": "set_responsible",
            "card_id": card_id,
            "owner_id": owner_id,
        },
    }


async def _invite_to_space(
    client: KaitenClient,
    space_id: int,
    email: str,
    space_name: Optional[str],
    role_id: Optional[str],
    guest: bool,
    send_email: bool,
    ctx: Optional[Any],
) -> Dict[str, Any]:
    """Invite a user to a space by email.

    Uses Kaiten API: POST /spaces/{space_id}/users
    Required: email
    Optional: role_id, guest, send_email

    Preset roles:
        - reader: '06ccb31f-426b-4fa3-b7e5-861daee95696'
        - writer: 'a431ed00-1b32-4cc7-92b6-85e4bc7de40e'
        - admin:  '07ea3efc-a004-4d31-8683-4bb2084e209b'
    """
    if ctx:
        await ctx.report_progress(progress=70, total=100)
        ctx.debug("Sending invite API request")

    invite_data: Dict[str, Any] = {"email": email}
    if role_id:
        invite_data["role_id"] = role_id
    invite_data["guest"] = guest
    invite_data["send_email"] = send_email

    response: Dict[str, Any] = await client.post(
        f"spaces/{space_id}/users", invite_data
    )

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"User invited to space: {space_id}")

    space_display = space_name or f"space ID {space_id}"
    role_suffix = f" (role: {role_id})" if role_id else ""
    guest_suffix = " as guest" if guest else ""
    return {
        "content": [
            {
                "type": "text",
                "text": f"User '{email}' invited to {space_display}{role_suffix}{guest_suffix}",
            }
        ],
        "structured_content": response,
        "meta": {
            "operation": "invite_to_space",
            "space_id": space_id,
            "email": email,
            "role_id": role_id,
            "guest": guest,
        },
    }


async def _remove_from_space(
    client: KaitenClient,
    space_id: int,
    user_id: int,
    user_name: Optional[str],
    space_name: Optional[str],
    ctx: Optional[Any],
) -> Dict[str, Any]:
    """Remove a user from a space.

    Uses Kaiten API: DELETE /spaces/{space_id}/users/{user_id}
    """
    if ctx:
        await ctx.report_progress(progress=70, total=100)
        ctx.debug("Sending remove from space API request")

    await client.delete(f"spaces/{space_id}/users/{user_id}")

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"User removed from space: {space_id}")

    user_display = user_name or f"user ID {user_id}"
    space_display = space_name or f"space ID {space_id}"
    return {
        "content": [
            {
                "type": "text",
                "text": f"User '{user_display}' (ID: {user_id}) removed from {space_display}",
            }
        ],
        "structured_content": {"success": True},
        "meta": {
            "operation": "remove_from_space",
            "space_id": space_id,
            "user_id": user_id,
        },
    }


async def _list_space_members(
    client: KaitenClient,
    space_id: int,
    space_name: Optional[str],
    ctx: Optional[Any],
) -> Dict[str, Any]:
    """List all members of a space.

    Uses Kaiten API: GET /spaces/{space_id}/users
    """
    if ctx:
        await ctx.report_progress(progress=50, total=100)
        ctx.debug("Fetching space members")

    response: Union[Dict[str, Any], List[Dict[str, Any]]] = await client.get(
        f"spaces/{space_id}/users"
    )

    members: List[Dict[str, Any]]
    if isinstance(response, list):
        members = response
    elif isinstance(response, dict) and "users" in response:
        members = response["users"]
    elif isinstance(response, dict) and "data" in response:
        members = response["data"]
    else:
        members = [response] if response else []

    if ctx:
        await ctx.report_progress(progress=100, total=100)
        ctx.info(f"Retrieved {len(members)} space members")

    space_display = space_name or f"Space ID {space_id}"
    parts: List[str] = [f"👥 Members of {space_display}:"]
    for member in members:
        member_name = member.get("full_name", member.get("name", "N/A"))
        member_id = member.get("id", member.get("user_id", "N/A"))
        role = member.get("role", "")
        role_suffix = f" [{role}]" if role else ""
        parts.append(f"  • {member_name} (ID: {member_id}){role_suffix}")

    text = "\n".join(parts) if members else f"No members found in {space_display}."

    return {
        "content": [{"type": "text", "text": text}],
        "structured_content": {"members": members},
        "meta": {
            "operation": "list_space_members",
            "space_id": space_id,
            "members_count": len(members),
        },
    }


@mcp.tool(
    name="manage_members",
    description=(
        "Unified tool for member operations on cards AND spaces. "
        "Card actions: add, remove, list, set_responsible (require card_id). "
        "Space actions: invite_to_space (requires email), remove_from_space, list_space_members. "
        "IMPORTANT: For card actions, pass 'user_name' with user NAME - ID is resolved automatically. "
        "For invite_to_space, pass 'email' (required by Kaiten API). "
        "Pass 'space' with space NAME - ID is resolved automatically. "
        "Examples: "
        "manage_members(action='set_responsible', card_id=123, owner_name='Ivanov'); "
        "manage_members(action='invite_to_space', space='Marketing', email='user@company.com'); "
        "manage_members(action='remove_from_space', space='Sales', user_name='Petrov'); "
        "manage_members(action='list_space_members', space='Sales')"
    ),
)
async def manage_members(
    action: Literal[
        "add",
        "remove",
        "list",
        "set_responsible",
        "invite_to_space",
        "remove_from_space",
        "list_space_members",
    ] = Field(..., description="Action to perform"),
    card_id: Optional[int] = Field(
        None,
        description="Card ID (required for card actions: add/remove/list/set_responsible)",
        gt=0,
    ),
    space_id: Optional[int] = Field(
        None,
        description="Space ID (for space actions)",
        gt=0,
    ),
    space: Optional[str] = Field(
        None,
        description="Space name - automatically resolved to ID, preferred over space_id",
    ),
    user_id: Optional[int] = Field(
        None,
        description="User ID (required for add/remove/remove_from_space)",
        gt=0,
    ),
    user_name: Optional[str] = Field(
        None,
        description="User name - automatically resolved to ID, preferred over user_id",
    ),
    email: Optional[str] = Field(
        None,
        description="User email (required for invite_to_space action)",
    ),
    role_id: Optional[str] = Field(
        None,
        description=(
            "Role ID for invite_to_space. Preset roles: "
            "reader='06ccb31f-426b-4fa3-b7e5-861daee95696', "
            "writer='a431ed00-1b32-4cc7-92b6-85e4bc7de40e', "
            "admin='07ea3efc-a004-4d31-8683-4bb2084e209b'"
        ),
    ),
    guest: bool = Field(
        False,
        description="Set true to invite user as guest (for invite_to_space)",
    ),
    send_email: bool = Field(
        True,
        description="Whether to send invitation email (for invite_to_space)",
    ),
    owner_id: Optional[int] = Field(
        None, description="Owner ID (required for set_responsible)", gt=0
    ),
    owner_name: Optional[str] = Field(
        None,
        description="Owner name - automatically resolved to ID, preferred over owner_id",
    ),
    ctx: Optional[Any] = None,
) -> Dict[str, Any]:
    """Unified member management tool for cards and spaces.

    Args:
        action: Operation to perform.
            Card actions: add/remove/list/set_responsible.
            Space actions: invite_to_space/remove_from_space/list_space_members.
        card_id: Identifier of the card (for card actions).
        space_id: Identifier of the space (for space actions).
        space: Space name (alternative to space_id, auto-resolved).
        user_id: User identifier for add/remove/remove_from_space.
        user_name: User name (alternative to user_id, auto-resolved).
        email: User email (required for invite_to_space).
        role_id: Role ID for invite_to_space.
        guest: Invite as guest (for invite_to_space).
        send_email: Send invitation email (for invite_to_space).
        owner_id: Owner identifier for set_responsible.
        owner_name: Owner name (alternative to owner_id, auto-resolved).
        ctx: Logging and progress context.

    Returns:
        dict: Operation result with content, structured_content, and meta.

    Raises:
        ValueError: If required parameters are missing.
        Exception: If API request fails.
    """
    if ctx:
        ctx.info(
            f"manage_members: action={action}, card_id={card_id}, space_id={space_id}"
        )
        await ctx.report_progress(progress=0, total=100)

    client = get_kaiten_client()

    try:
        # Card member actions
        if action == "add":
            if card_id is None:
                raise ValueError("card_id is required for 'add' action")
            resolved_user_id = await _resolve_user_id(client, user_id, user_name, ctx)
            return await _add_member(client, card_id, resolved_user_id, user_name, ctx)

        if action == "remove":
            if card_id is None:
                raise ValueError("card_id is required for 'remove' action")
            resolved_user_id = await _resolve_user_id(client, user_id, user_name, ctx)
            return await _remove_member(
                client, card_id, resolved_user_id, user_name, ctx
            )

        if action == "list":
            if card_id is None:
                raise ValueError("card_id is required for 'list' action")
            return await _list_members(client, card_id, ctx)

        if action == "set_responsible":
            if card_id is None:
                raise ValueError("card_id is required for 'set_responsible' action")
            resolved_owner_id = await _resolve_user_id(
                client, owner_id, owner_name, ctx
            )
            return await _set_responsible(
                client, card_id, resolved_owner_id, owner_name, ctx
            )

        # Space member actions
        if action == "invite_to_space":
            if not email:
                raise ValueError("email is required for 'invite_to_space' action")
            resolved_space_id = await _resolve_space_id(client, space_id, space, ctx)
            return await _invite_to_space(
                client, resolved_space_id, email, space, role_id, guest, send_email, ctx
            )

        if action == "remove_from_space":
            resolved_space_id = await _resolve_space_id(client, space_id, space, ctx)
            resolved_user_id = await _resolve_user_id(client, user_id, user_name, ctx)
            return await _remove_from_space(
                client, resolved_space_id, resolved_user_id, user_name, space, ctx
            )

        if action == "list_space_members":
            resolved_space_id = await _resolve_space_id(client, space_id, space, ctx)
            return await _list_space_members(client, resolved_space_id, space, ctx)

        raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        error_msg = f"manage_members failed: {e}"
        if ctx:
            ctx.error(error_msg)
        raise

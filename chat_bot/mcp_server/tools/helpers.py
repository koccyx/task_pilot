"""Helper functions for board operations.

Business logic for working with Kaiten boards and spaces.
"""

import logging
from typing import Any, Dict, List, Optional, cast

from chat_bot.mcp_server.client.kaiten_client import KaitenClient

logger = logging.getLogger(__name__)


async def find_board_record_by_name(
    client: KaitenClient, board_name: str
) -> Optional[Dict[str, Any]]:
    """Find board metadata by its name across all spaces.

    Returns a normalized record with at least ``id`` and ``space_id`` when found.
    Matching is case-insensitive.
    """
    logger.debug("Looking for board record: %s", board_name)
    board_name_lower = board_name.lower()

    spaces_response = await client.get("spaces")
    logger.debug("Received spaces response")

    spaces: List[Dict[str, Any]]
    if isinstance(spaces_response, list):
        spaces = spaces_response
    elif isinstance(spaces_response, dict) and "spaces" in spaces_response:
        spaces = spaces_response["spaces"]
    else:
        spaces = [spaces_response] if spaces_response else []

    logger.debug("Found %d spaces", len(spaces))

    for space in spaces:
        space_id = space.get("id")
        space_name = space.get("name", space.get("title", "Unknown"))
        logger.debug("Checking space: %s (ID: %s)", space_name, space_id)

        try:
            boards_response = await client.get(f"spaces/{space_id}/boards")

            boards: List[Dict[str, Any]]
            if isinstance(boards_response, list):
                boards = boards_response
            elif isinstance(boards_response, dict) and "boards" in boards_response:
                boards = boards_response["boards"]
            else:
                boards = [boards_response] if boards_response else []

            logger.debug("Found %d boards in space %s", len(boards), space_name)

            for board in boards:
                for field in ("title", "name"):
                    value = board.get(field)
                    if isinstance(value, str) and value.lower() == board_name_lower:
                        normalized_board = dict(board)
                        normalized_board.setdefault("space_id", space_id)
                        logger.info(
                            "Found board '%s' with ID: %s in space '%s'",
                            board_name,
                            normalized_board.get("id"),
                            space_name,
                        )
                        return normalized_board
        except Exception as e:
            logger.warning(
                "Failed to fetch boards from space %s: %s",
                space_name,
                str(e),
            )
            continue

    logger.warning("Board not found: %s", board_name)
    return None


async def find_board_by_name(client: KaitenClient, board_name: str) -> Optional[int]:
    """Find board ID by its name across all spaces (case-insensitive).

    This is business logic - it knows about Kaiten's hierarchy
    (Spaces → Boards) and how to search through them.

    Args:
        client: HTTP client instance.
        board_name: Name of the board to find.

    Returns:
        Board ID if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    board = await find_board_record_by_name(client, board_name)
    if board is None:
        return None
    return cast(Optional[int], board.get("id"))


async def find_column_by_name(
    client: KaitenClient,
    column_name: str,
    board_id: Optional[int] = None,
    board_name: Optional[str] = None,
) -> Optional[int]:
    """Find column ID by its name within a board (case-insensitive).

    This is business logic - it knows about Kaiten's hierarchy
    (Boards → Columns) and how to search through them.

    Args:
        client: HTTP client instance.
        column_name: Name of the column to find.
        board_id: Optional board ID to search within.
        board_name: Optional board name to search within (alternative to board_id).

    Returns:
        Column ID if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Looking for column: %s", column_name)
    column_name_lower = column_name.lower()

    # Resolve board_id if board_name is provided
    resolved_board_id: Optional[int] = board_id
    if board_name is not None:
        found_board_id = await find_board_by_name(client, board_name)
        if found_board_id is None:
            logger.warning("Board not found: %s", board_name)
            return None
        resolved_board_id = found_board_id

    if resolved_board_id is None:
        logger.warning("Board ID or name must be provided to find column")
        return None

    try:
        # Get board details with columns
        board_response = await client.get(f"boards/{resolved_board_id}")
        logger.debug("Received board response")

        # Try to get columns from board response
        columns: List[Dict[str, Any]] = []
        if isinstance(board_response, dict):
            # Try different possible field names
            for field in ("columns", "column_ids", "cells"):
                if field in board_response:
                    columns_data = board_response[field]
                    if isinstance(columns_data, list):
                        columns = columns_data
                        break

        # If columns not found in board response, try to get them separately
        if not columns:
            try:
                columns_response = await client.get(
                    f"boards/{resolved_board_id}/columns"
                )
                if isinstance(columns_response, list):
                    columns = columns_response
                elif (
                    isinstance(columns_response, dict) and "columns" in columns_response
                ):
                    columns = columns_response["columns"]
            except Exception as e:
                logger.warning("Failed to fetch columns separately: %s", str(e))

        logger.debug("Found %d columns in board %s", len(columns), resolved_board_id)

        # Search for column by name
        for column in columns:
            # Try different field names that might contain column title
            for field in ("title", "name", "label"):
                if field in column:
                    if column[field].lower() == column_name_lower:
                        column_id = column.get("id")
                        logger.info(
                            "Found column '%s' with ID: %s in board %s",
                            column_name,
                            column_id,
                            resolved_board_id,
                        )
                        return column_id

        logger.warning(
            "Column '%s' not found in board %s", column_name, resolved_board_id
        )
        return None

    except Exception as e:
        logger.error(
            "Failed to find column '%s' in board %s: %s",
            column_name,
            resolved_board_id,
            str(e),
        )
        return None


async def find_space_by_name(client: KaitenClient, space_name: str) -> Optional[int]:
    """Find space ID by its name (case-insensitive).

    This is business logic - it knows about Kaiten's hierarchy
    and how to search through spaces.

    Args:
        client: HTTP client instance.
        space_name: Name of the space to find.

    Returns:
        Space ID if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Looking for space: %s", space_name)
    space_name_lower = space_name.lower()

    # Get all spaces
    spaces_response = await client.get("spaces")
    logger.debug("Received spaces response")

    # Handle different response formats
    spaces: List[Dict[str, Any]]
    if isinstance(spaces_response, list):
        spaces = spaces_response
    elif isinstance(spaces_response, dict) and "spaces" in spaces_response:
        spaces = spaces_response["spaces"]
    else:
        spaces = [spaces_response] if spaces_response else []

    logger.debug("Found %d spaces", len(spaces))

    # Search for space by name
    for space in spaces:
        # Try different field names that might contain space title
        for field in ("title", "name"):
            if field in space:
                if space[field].lower() == space_name_lower:
                    space_id = space.get("id")
                    logger.info(
                        "Found space '%s' with ID: %s",
                        space_name,
                        space_id,
                    )
                    return space_id

    logger.warning("Space not found: %s", space_name)
    return None


async def find_user_by_name(client: KaitenClient, user_name: str) -> Optional[int]:
    """Find user ID by name (case-insensitive partial match).

    This is business logic - it searches through all users
    to find a match by name. Supports matching by:
    - full_name (e.g., "Тимур Черяпов")
    - username (e.g., "timurchery")
    - partial first/last name (e.g., "Тимур" matches "Тимур Черяпов")

    Args:
        client: HTTP client instance.
        user_name: Name of the user to find (can be partial).

    Returns:
        User ID if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Looking for user: %s", user_name)
    user_name_lower = user_name.lower().strip()

    try:
        # Get all users
        users_response = await client.get("users")
        logger.debug("Received users response")

        # Handle different response formats
        users: List[Dict[str, Any]]
        if isinstance(users_response, list):
            users = users_response
        elif isinstance(users_response, dict) and "users" in users_response:
            users = users_response["users"]
        elif isinstance(users_response, dict) and "data" in users_response:
            users = users_response["data"]
        else:
            users = [users_response] if users_response else []

        logger.debug("Found %d users", len(users))

        # First pass: try exact match
        for user in users:
            for field in ("full_name", "name", "username", "display_name"):
                if field in user and user[field]:
                    user_field_value = str(user[field]).lower().strip()
                    if user_field_value == user_name_lower:
                        user_id = user.get("id")
                        logger.info(
                            "Found user '%s' with ID: %s (exact match on %s)",
                            user_name,
                            user_id,
                            field,
                        )
                        return user_id

        # Second pass: try partial match (search name in full_name)
        for user in users:
            for field in ("full_name", "name", "display_name"):
                if field in user and user[field]:
                    user_field_value = str(user[field]).lower().strip()
                    # Check if search term is contained in the field
                    if user_name_lower in user_field_value:
                        user_id = user.get("id")
                        logger.info(
                            "Found user '%s' with ID: %s (partial match on %s='%s')",
                            user_name,
                            user_id,
                            field,
                            user[field],
                        )
                        return user_id
                    # Also check if any word in full_name starts with search term
                    words = user_field_value.split()
                    for word in words:
                        if word.startswith(user_name_lower):
                            user_id = user.get("id")
                            logger.info(
                                "Found user '%s' with ID: %s (word match on %s='%s')",
                                user_name,
                                user_id,
                                field,
                                user[field],
                            )
                            return user_id

        logger.warning("User not found: %s", user_name)
        return None

    except Exception as e:
        logger.error("Failed to find user '%s': %s", user_name, str(e))
        return None


async def find_card_by_title(
    client: KaitenClient,
    card_title: str,
    board_id: Optional[int] = None,
    board_name: Optional[str] = None,
) -> Optional[int]:
    """Find card ID by title (case-insensitive partial match).

    Args:
        client: HTTP client instance.
        card_title: Title of the card to find.
        board_id: Optional board ID to search within.
        board_name: Optional board name to search within.

    Returns:
        Card ID if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Looking for card: %s", card_title)
    card_title_lower = card_title.lower().strip()

    resolved_board_id = board_id
    if board_name is not None:
        found_board_id = await find_board_by_name(client, board_name)
        if found_board_id is None:
            logger.warning("Board not found: %s", board_name)
            return None
        resolved_board_id = found_board_id

    try:
        params = "condition=1"
        if resolved_board_id is not None:
            params += f"&board_id={resolved_board_id}"

        cards_response = await client.get(f"cards?{params}")

        cards: List[Dict[str, Any]]
        if isinstance(cards_response, list):
            cards = cards_response
        elif isinstance(cards_response, dict) and "cards" in cards_response:
            cards = cards_response["cards"]
        elif isinstance(cards_response, dict) and "data" in cards_response:
            cards = cards_response["data"]
        else:
            cards = [cards_response] if cards_response else []

        logger.debug("Found %d cards to search through", len(cards))

        for card in cards:
            title = card.get("title", "")
            if title.lower().strip() == card_title_lower:
                card_id = card.get("id")
                logger.info(
                    "Found card '%s' with ID: %s (exact match)", card_title, card_id
                )
                return card_id

        for card in cards:
            title = card.get("title", "")
            if card_title_lower in title.lower():
                card_id = card.get("id")
                logger.info(
                    "Found card '%s' with ID: %s (partial match on '%s')",
                    card_title,
                    card_id,
                    title,
                )
                return card_id

        logger.warning("Card not found: %s", card_title)
        return None

    except Exception as e:
        logger.error("Failed to find card '%s': %s", card_title, str(e))
        return None


async def get_active_sprint(
    client: KaitenClient, board_id: int
) -> Optional[Dict[str, Any]]:
    """Get active sprint for a board.

    Args:
        client: HTTP client instance.
        board_id: Identifier of the board.

    Returns:
        Active sprint dictionary if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Looking for active sprint on board: %s", board_id)

    try:
        sprints_response = await client.get("/sprints")

        for sprint in sprints_response:
            is_active = sprint.get("active", False)
            if is_active and board_id == sprint.get("board_id"):
                logger.info("Found active sprint: %s", sprint.get("id"))
                return sprint

        logger.warning("No active sprint found on board %s", board_id)
        return None

    except Exception as e:
        logger.error("Failed to get active sprint: %s", str(e))
        return None


async def find_column_by_type(
    client: KaitenClient, board_id: int, column_type: int
) -> Optional[int]:
    """Find column ID by type on a board.

    Args:
        client: HTTP client instance.
        board_id: Identifier of the board.
        column_type: Column type (1=Queue, 2=In Progress, 3=Done).

    Returns:
        Column ID if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Looking for column type %s on board: %s", column_type, board_id)

    try:
        board_response = await client.get(f"boards/{board_id}")
        columns = board_response.get("columns", [])

        for column in columns:
            if column.get("type") == column_type:
                column_id = cast(Optional[int], column.get("id"))
                logger.info("Found column type %s with ID: %s", column_type, column_id)
                return column_id

        # If not found in board response, try columns endpoint
        columns_response = await client.get(f"boards/{board_id}/columns")
        columns_list: List[Dict[str, Any]]
        if isinstance(columns_response, list):
            columns_list = columns_response
        elif isinstance(columns_response, dict) and "columns" in columns_response:
            columns_list = columns_response["columns"]
        else:
            columns_list = [columns_response] if columns_response else []

        for column in columns_list:
            if column.get("type") == column_type:
                column_id = cast(Optional[int], column.get("id"))
                logger.info("Found column type %s with ID: %s", column_type, column_id)
                return column_id

        logger.warning("Column type %s not found on board %s", column_type, board_id)
        return None

    except Exception as e:
        logger.error("Failed to find column by type: %s", str(e))
        return None


async def get_done_columns(client: KaitenClient, board_id: int) -> List[int]:
    """Get all Done columns (type=3) for a board.

    Args:
        client: HTTP client instance.
        board_id: Identifier of the board.

    Returns:
        List of Done column IDs.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Getting Done columns for board: %s", board_id)

    try:
        board_response = await client.get(f"boards/{board_id}")
        columns = board_response.get("columns", [])

        done_columns: List[int] = []
        for column in columns:
            if column.get("type") == 3:  # Done
                column_id = column.get("id")
                if column_id:
                    done_columns.append(column_id)

        # If not found in board response, try columns endpoint
        if not done_columns:
            columns_response = await client.get(f"boards/{board_id}/columns")
            columns_list: List[Dict[str, Any]]
            if isinstance(columns_response, list):
                columns_list = columns_response
            elif isinstance(columns_response, dict) and "columns" in columns_response:
                columns_list = columns_response["columns"]
            else:
                columns_list = [columns_response] if columns_response else []

            for column in columns_list:
                if column.get("type") == 3:  # Done
                    column_id = column.get("id")
                    if column_id:
                        done_columns.append(column_id)

        logger.info("Found %d Done columns on board %s", len(done_columns), board_id)
        return done_columns

    except Exception as e:
        logger.error("Failed to get Done columns: %s", str(e))
        return []


async def find_tag_by_name(
    client: KaitenClient, tag_name: str, card_id: Optional[int] = None
) -> Optional[int]:
    """Find tag ID by its name (case-insensitive).

    Args:
        client: HTTP client instance.
        tag_name: Name of the tag to find.
        card_id: Optional card ID to filter tags.

    Returns:
        Tag ID if found, None otherwise.

    Raises:
        Exception: If API request fails.
    """
    logger.debug("Looking for tag: %s", tag_name)
    tag_name_lower = tag_name.lower().strip()

    try:
        endpoint = "tags"
        if card_id:
            endpoint = f"tags?card_id={card_id}"

        tags_response = await client.get(endpoint)

        tags: List[Dict[str, Any]]
        if isinstance(tags_response, list):
            tags = tags_response
        elif isinstance(tags_response, dict) and "tags" in tags_response:
            tags = tags_response["tags"]
        else:
            tags = [tags_response] if tags_response else []

        logger.debug("Found %d tags to search through", len(tags))

        for tag in tags:
            name = tag.get("name", "")
            if name.lower().strip() == tag_name_lower:
                tag_id = tag.get("id")
                logger.info(
                    "Found tag '%s' with ID: %s (exact match)", tag_name, tag_id
                )
                return tag_id

        logger.warning("Tag not found: %s", tag_name)
        return None

    except Exception as e:
        logger.error("Failed to find tag '%s': %s", tag_name, str(e))
        return None

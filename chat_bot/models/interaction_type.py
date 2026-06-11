"""
InteractionType enum for distinguishing conversation modes.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InteractionType(str, Enum):
    """Enum for types of bot interaction."""

    NEW_CONVERSATION = "new_conversation"
    REPLY_TO_BOT = "reply_to_bot"
    NOT_FOR_BOT = "not_for_bot"


class InteractionInfo(BaseModel):
    """Model containing interaction details."""

    interaction_type: InteractionType = Field(
        ..., description="Type of interaction with the bot"
    )
    reply_to_message_id: Optional[int] = Field(
        None, description="ID of the bot message being replied to"
    )

"""
MessagesData model for a collection of messages.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, validator

from .message import Message


class MessagesData(BaseModel):
    """Model for a collection of messages."""

    messages: List[Message] = Field(
        default_factory=list, description="List of messages"
    )

    @classmethod
    @validator("messages")
    def validate_messages(cls, v: Optional[List[Message]]) -> List[Message]:
        """Validate that messages list is not None."""
        if v is None:
            return []
        return v

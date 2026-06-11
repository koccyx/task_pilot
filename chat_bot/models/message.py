"""
Message model for a single chat message.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class Message(BaseModel):
    """Model for a single chat message."""

    timestamp: str = Field(..., description="ISO format timestamp of the message")
    message_id: int = Field(..., description="Telegram message ID")
    sender_name: str = Field(..., description="Name of the message sender")
    telegram_user_id: Optional[int] = Field(
        None, description="Telegram user ID of the sender"
    )
    telegram_username: Optional[str] = Field(
        None, description="Telegram username of the sender"
    )
    text: Optional[str] = Field(None, description="Message text content")
    reply_to_message_id: Optional[int] = Field(
        None, description="ID of the message being replied to"
    )
    is_bot_message: bool = Field(
        False, description="Whether the message is from the bot"
    )

    @classmethod
    @validator("timestamp")
    def validate_timestamp(cls, v: str) -> str:
        """Validate that timestamp is in ISO format."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except ValueError:
            raise ValueError("timestamp must be in ISO format")

    @classmethod
    @validator("message_id")
    def validate_message_id(cls, v: int) -> int:
        """Validate that message_id is positive."""
        if v <= 0:
            raise ValueError("message_id must be positive")
        return v

    @classmethod
    @validator("sender_name")
    def validate_sender_name(cls, v: str) -> str:
        """Validate that sender_name is not empty."""
        if not v or not v.strip():
            raise ValueError("sender_name cannot be empty")
        return v.strip()

    @classmethod
    @validator("reply_to_message_id")
    def validate_reply_to_message_id(cls, v: Optional[int]) -> Optional[int]:
        """Validate that reply_to_message_id is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError("reply_to_message_id must be positive")
        return v

    @classmethod
    @validator("telegram_user_id")
    def validate_telegram_user_id(cls, v: Optional[int]) -> Optional[int]:
        """Validate that telegram_user_id is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError("telegram_user_id must be positive")
        return v

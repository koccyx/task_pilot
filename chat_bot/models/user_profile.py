"""
User profile model for Telegram identity memory.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class UserProfile(BaseModel):
    """Persistent identity profile for a Telegram user in a chat."""

    chat_id: int = Field(..., description="Telegram chat ID")
    telegram_user_id: int = Field(..., description="Telegram user ID")
    telegram_username: Optional[str] = Field(None, description="Telegram username")
    telegram_display_name: str = Field(..., description="Current Telegram display name")
    introduced_name: str = Field(..., description="Name provided by the user")
    kaiten_user_name: Optional[str] = Field(
        None, description="Optional Kaiten display name or username"
    )
    kaiten_user_id: Optional[int] = Field(
        None, description="Optional stable Kaiten user ID"
    )
    is_admin: bool = Field(
        False, description="Whether the user has Task Pilot admin privileges"
    )
    introduced_at: Optional[datetime] = Field(
        None, description="When the user introduced themselves"
    )
    updated_at: Optional[datetime] = Field(
        None, description="When the profile was updated"
    )

    @classmethod
    @validator("telegram_user_id", "chat_id")
    def validate_positive_ids(cls, v: int) -> int:
        """Validate positive identifiers."""
        if v <= 0:
            raise ValueError("identifier must be positive")
        return v

    @classmethod
    @validator("kaiten_user_id")
    def validate_optional_positive_id(cls, v: Optional[int]) -> Optional[int]:
        """Validate the optional Kaiten identifier."""
        if v is not None and v <= 0:
            raise ValueError("identifier must be positive")
        return v

    @classmethod
    @validator("telegram_display_name", "introduced_name")
    def validate_non_empty(cls, v: str) -> str:
        """Validate required string fields."""
        if not v or not v.strip():
            raise ValueError("value cannot be empty")
        return v.strip()

    @classmethod
    @validator("telegram_username", "kaiten_user_name")
    def normalize_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        """Normalize optional string fields."""
        if v is None:
            return None
        normalized = v.strip()
        return normalized or None

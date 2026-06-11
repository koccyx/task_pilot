"""
BotConfig model for bot configuration.
"""

from typing import Optional

from pydantic import BaseModel, Field, validator

from .postgres_config import PostgresConfig


class BotConfig(BaseModel):
    """Model for bot configuration."""

    token: str = Field(..., description="Telegram bot token")
    postgres_config: Optional[PostgresConfig] = Field(
        None, description="PostgreSQL configuration for storage"
    )

    @classmethod
    @validator("token")
    def validate_token(cls, v: str) -> str:
        """Validate that token is not empty."""
        if not v or not v.strip():
            raise ValueError("token cannot be empty")
        return v.strip()

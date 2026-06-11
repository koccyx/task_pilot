"""Configuration settings for task_pilot MCP Server."""

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()


class Settings(BaseModel):
    """Application settings loaded from environment variables.

    Attributes:
        kaiten_api_url: Base URL for Kaiten API.
        kaiten_api_token: Bearer token for Kaiten API authentication.
    """

    kaiten_api_url: str = Field(
        ...,
        description="Base URL for Kaiten API",
    )
    kaiten_api_token: str = Field(
        ...,
        description="Bearer token for Kaiten API authentication",
    )

    @field_validator("kaiten_api_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate that URL is not empty."""
        if not v or not v.strip():
            raise ValueError("KAITEN_API_URL cannot be empty")
        return v.strip().rstrip("/")

    @field_validator("kaiten_api_token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        """Validate that token is not empty."""
        if not v or not v.strip():
            raise ValueError("KAITEN_API_TOKEN cannot be empty")
        return v.strip()

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings instance from environment variables.

        Returns:
            Settings instance with loaded configuration.

        Raises:
            ValueError: If required environment variables are missing.
        """
        api_url: Optional[str] = os.getenv("KAITEN_API_URL")
        api_token: Optional[str] = os.getenv("KAITEN_API_TOKEN")

        if not api_url:
            raise ValueError("KAITEN_API_URL environment variable is required")
        if not api_token:
            raise ValueError("KAITEN_API_TOKEN environment variable is required")

        return cls(
            kaiten_api_url=api_url,
            kaiten_api_token=api_token,
        )

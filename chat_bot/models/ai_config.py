"""
AIConfig model for AI configuration.
"""

from typing import Optional

from pydantic import BaseModel, Field, validator


class AIConfig(BaseModel):
    """Model for AI configuration."""

    api_key: str = Field(..., description="AI API key")
    model: str = Field("t-tech/T-pro-it-2.0", description="AI model name")
    base_url: Optional[str] = Field(None, description="Custom AI base URL")
    project: Optional[str] = Field(None, description="Provider-specific project/folder")
    light_api_key: Optional[str] = Field(None, description="Light AI API key")
    light_model: Optional[str] = Field(None, description="Light AI model name")
    light_base_url: Optional[str] = Field(None, description="Custom light AI base URL")
    temperature: float = Field(
        0.3, ge=0.0, le=2.0, description="Generation temperature"
    )
    max_tokens: int = Field(500, gt=0, description="Maximum tokens for generation")
    light_temperature: float = Field(
        0.0, ge=0.0, le=2.0, description="Light model generation temperature"
    )
    light_max_tokens: int = Field(
        500, gt=0, description="Maximum tokens for light model generation"
    )

    @classmethod
    @validator("api_key")
    def validate_api_key(cls, v: str) -> str:
        """Validate that API key is not empty."""
        if not v or not v.strip():
            raise ValueError("api_key cannot be empty")
        return v.strip()

    @classmethod
    @validator("model")
    def validate_model(cls, v: str) -> str:
        """Validate that model name is not empty."""
        if not v or not v.strip():
            raise ValueError("model cannot be empty")
        return v.strip()

    @classmethod
    @validator("light_api_key", "light_model", "light_base_url")
    def validate_optional_light_value(cls, v: Optional[str]) -> Optional[str]:
        """Normalize optional light model configuration values."""
        if v is None:
            return None
        normalized = v.strip()
        return normalized or None

    @classmethod
    @validator("project")
    def validate_project(cls, v: Optional[str]) -> Optional[str]:
        """Normalize optional project/folder value."""
        if v is None:
            return None
        normalized = v.strip()
        return normalized or None

    @classmethod
    @validator("temperature")
    def validate_temperature(cls, v: float) -> float:
        """Validate temperature range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v

    @classmethod
    @validator("max_tokens")
    def validate_max_tokens(cls, v: int) -> int:
        """Validate max_tokens is positive."""
        if v <= 0:
            raise ValueError("max_tokens must be positive")
        return v

    @classmethod
    @validator("light_max_tokens")
    def validate_light_max_tokens(cls, v: int) -> int:
        """Validate light max_tokens is positive."""
        if v <= 0:
            raise ValueError("light_max_tokens must be positive")
        return v

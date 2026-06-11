"""
PostgreSQL configuration model.
"""

from pydantic import BaseModel, Field, validator


class PostgresConfig(BaseModel):
    """Model for PostgreSQL configuration."""

    database_url: str = Field(..., description="PostgreSQL connection string")

    @classmethod
    @validator("database_url")
    def validate_database_url(cls, v: str) -> str:
        """Validate that database_url is not empty."""
        if not v or not v.strip():
            raise ValueError("database_url cannot be empty")
        return v.strip()

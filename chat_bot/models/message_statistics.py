"""
MessageStatistics model for message statistics.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, validator


class MessageStatistics(BaseModel):
    """Model for message statistics."""

    total_messages: int = Field(0, description="Total number of messages")
    unique_senders: int = Field(0, description="Number of unique senders")
    senders: Dict[str, int] = Field(
        default_factory=dict, description="Message count per sender"
    )
    time_range: Optional[Dict[str, Any]] = Field(
        None, description="Time range information"
    )

    @classmethod
    @validator("total_messages", "unique_senders")
    def validate_non_negative(cls, v: int) -> int:
        """Validate that counts are non-negative."""
        if v < 0:
            raise ValueError("Count must be non-negative")
        return v

    @classmethod
    @validator("senders")
    def validate_senders(cls, v: Dict[str, int]) -> Dict[str, int]:
        """Validate that sender counts are positive."""
        for sender, count in v.items():
            if count <= 0:
                raise ValueError(f"Sender count for {sender} must be positive")
        return v

"""Pydantic model for Kaiten time log."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TimeLog(BaseModel):
    """Model representing a Kaiten time log.

    Attributes:
        id: Unique identifier of the time log (optional for creation).
        card_id: Identifier of the card.
        role_id: Identifier of the role.
        time_spent: Time spent in minutes.
        for_date: Date in YYYY-MM-DD format.
        comment: Optional comment.
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the time log",
    )
    card_id: int = Field(
        ...,
        description="Identifier of the card",
        gt=0,
    )
    role_id: int = Field(
        ...,
        description="Identifier of the role (-1 is the predefined Employee role)",
        ge=-1,
    )
    time_spent: int = Field(
        ...,
        description="Time spent in minutes",
        gt=0,
    )
    for_date: str = Field(
        ...,
        description="Date in YYYY-MM-DD format",
    )
    comment: Optional[str] = Field(
        None,
        description="Optional comment",
    )

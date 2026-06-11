"""Pydantic model for Kaiten card."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Card(BaseModel):
    """Model representing a Kaiten card.

    Attributes:
        id: Unique identifier of the card (optional for creation).
        title: Title of the card.
        board_id: Identifier of the board containing the card.
        asap: Whether the card is urgent.
        due_date: Due date of the card in YYYY-MM-DD format.
        description: Description of the card (optional).
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the card",
    )
    title: str = Field(
        ...,
        description="Title of the card",
        min_length=1,
    )
    board_id: int = Field(
        ...,
        description="Identifier of the board containing the card",
        gt=0,
    )
    asap: bool = Field(
        False,
        description="Whether the card is urgent",
    )
    due_date: Optional[str] = Field(
        None,
        description="Due date of the card in YYYY-MM-DD format",
    )
    description: Optional[str] = Field(
        None,
        description="Description of the card",
    )

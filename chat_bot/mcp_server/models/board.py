"""Pydantic model for Kaiten board."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Board(BaseModel):
    """Model representing a Kaiten board.

    Attributes:
        id: Unique identifier of the board (optional for creation).
        title: Title of the board.
        space_id: Identifier of the space containing the board.
        description: Description of the board (optional).
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the board",
    )
    title: str = Field(
        ...,
        description="Title of the board",
        min_length=1,
    )
    space_id: int = Field(
        ...,
        description="Identifier of the space containing the board",
        gt=0,
    )
    description: Optional[str] = Field(
        None,
        description="Description of the board",
    )

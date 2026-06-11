"""Pydantic model for Kaiten column."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Column(BaseModel):
    """Model representing a Kaiten board column.

    Attributes:
        id: Unique identifier of the column (optional for creation).
        title: Title of the column.
        board_id: Identifier of the board containing the column.
        column_type: Type of the column (e.g., queue, in_progress, done).
        sort_order: Order position of the column on the board.
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the column",
    )
    title: str = Field(
        ...,
        description="Title of the column",
        min_length=1,
    )
    board_id: int = Field(
        ...,
        description="Identifier of the board containing the column",
        gt=0,
    )
    column_type: Optional[str] = Field(
        None,
        description="Type of the column (e.g., queue, in_progress, done)",
    )
    sort_order: Optional[int] = Field(
        None,
        description="Order position of the column on the board",
        ge=0,
    )

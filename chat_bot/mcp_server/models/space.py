"""Pydantic model for Kaiten space."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Space(BaseModel):
    """Model representing a Kaiten space.

    Attributes:
        id: Unique identifier of the space (optional for creation).
        title: Title of the space.
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the space",
    )
    title: str = Field(
        ...,
        description="Title of the space",
        min_length=1,
        max_length=256,
    )

"""Pydantic model for Kaiten tag."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Tag(BaseModel):
    """Model representing a Kaiten tag.

    Attributes:
        id: Unique identifier of the tag (optional for creation).
        name: Name of the tag.
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the tag",
    )
    name: str = Field(
        ...,
        description="Name of the tag",
        min_length=1,
    )

"""Pydantic model for Kaiten user."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """Model representing a Kaiten user.

    Attributes:
        id: Unique identifier of the user.
        username: Username of the user.
        full_name: Full name of the user.
        email: Email address of the user.
        status: Status of the user (e.g., active, inactive).
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the user",
    )
    username: Optional[str] = Field(
        None,
        description="Username of the user",
    )
    full_name: Optional[str] = Field(
        None,
        description="Full name of the user",
    )
    email: Optional[str] = Field(
        None,
        description="Email address of the user",
    )
    status: Optional[str] = Field(
        None,
        description="Status of the user (e.g., active, inactive)",
    )

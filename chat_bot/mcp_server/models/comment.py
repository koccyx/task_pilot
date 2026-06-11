"""Pydantic model for Kaiten comment."""

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Comment(BaseModel):
    """Model representing a Kaiten comment.

    Attributes:
        id: Unique identifier of the comment (optional for creation).
        card_id: Identifier of the card containing the comment.
        text: Text content of the comment.
        author_id: Identifier of the comment author.
        attachments: Optional list of attachment objects.
        created_at: Timestamp when the comment was created.
        updated_at: Timestamp when the comment was last updated.
    """

    model_config = ConfigDict(
        frozen=False,
        extra="allow",
    )

    id: Optional[int] = Field(
        None,
        description="Unique identifier of the comment",
    )
    card_id: int = Field(
        ...,
        description="Identifier of the card containing the comment",
        gt=0,
    )
    text: str = Field(
        ...,
        description="Text content of the comment",
        min_length=1,
        max_length=4096,
    )

    @field_validator("text", mode="before")
    @classmethod
    def validate_text_not_whitespace(cls, value: str) -> str:
        """Validate that text is not empty or whitespace-only.

        Args:
            value: The text value to validate.

        Returns:
            str: The stripped text value.

        Raises:
            ValueError: If text is empty or whitespace-only.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("Comment text cannot be empty or whitespace-only")
            return stripped
        return value
    author_id: Optional[int] = Field(
        None,
        description="Identifier of the comment author",
        gt=0,
    )
    attachments: Optional[List[Any]] = Field(
        None,
        description="Optional list of attachment objects",
    )
    created_at: Optional[str] = Field(
        None,
        description="Timestamp when the comment was created",
    )
    updated_at: Optional[str] = Field(
        None,
        description="Timestamp when the comment was last updated",
    )

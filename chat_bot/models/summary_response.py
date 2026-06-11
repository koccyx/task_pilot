"""
SummaryResponse model for summary response.
"""

from typing import Optional

from pydantic import BaseModel, Field, validator


class SummaryOutput(BaseModel):
    """
    Structured output schema for summary generation from chat messages.

    This model is used with LangChain's structured output feature to ensure
    the AI model returns properly formatted summary data.
    """

    thoughts: str = Field(
        ...,
        description="The AI's reasoning process and thoughts about the messages before creating the summary. This should be in Russian.",
    )
    summary: str = Field(
        ...,
        description="The actual summary of the chat messages. This should be concise and in Russian.",
    )


class SummaryResponse(BaseModel):
    """Model for summary response."""

    summary: str = Field(..., description="Generated summary text")
    success: bool = Field(True, description="Whether summarization was successful")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    processing_time: Optional[float] = Field(
        None, description="Processing time in seconds"
    )

    @classmethod
    @validator("summary")
    def validate_summary(cls, v: str) -> str:
        """Validate that summary is not empty if successful."""
        if not v or not v.strip():
            raise ValueError("summary cannot be empty")
        return v.strip()

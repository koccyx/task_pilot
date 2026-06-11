"""
Structured output model for task extraction.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from .task import Task


class TaskExtractionOutput(BaseModel):
    """
    Structured output schema for task extraction from chat messages.

    This model is used with LangChain's structured output feature to ensure
    the AI model returns properly formatted task data.
    """

    tasks: List[Task] = Field(
        default_factory=list,
        description="List of tasks extracted from the chat messages. If no tasks are found, return an empty list.",
    )


class TaskExtractionResponse(BaseModel):
    """
    Response model for task extraction from chat messages.

    Attributes:
        tasks: List of extracted tasks
        success: Whether the extraction was successful
        error_message: Error message if extraction failed
        processing_time: Time taken to process the extraction
    """

    tasks: List[Task] = Field(
        ..., description="List of extracted tasks from the messages"
    )
    success: bool = Field(..., description="Whether the extraction was successful")
    error_message: Optional[str] = Field(
        None, description="Error message if extraction failed"
    )
    processing_time: float = Field(
        ..., description="Time taken to process the extraction in seconds"
    )

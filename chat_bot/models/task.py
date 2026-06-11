"""
Task model for extracted tasks from chat messages.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Task(BaseModel):
    """
    Represents a task extracted from chat messages.

    Attributes:
        assignee: The person assigned to the task
        title: The title/description of the task
        deadline: Optional deadline date/time for the task
    """

    assignee: str = Field(..., description="The person assigned to the task")
    title: str = Field(..., description="The title/description of the task")
    deadline: Optional[datetime] = Field(
        None, description="Optional deadline date/time for the task"
    )

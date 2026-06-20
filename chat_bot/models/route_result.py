"""Route result models for Telegram responses."""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RouteResult(BaseModel):
    """A routed response that may include an attached local file."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    document_path: Optional[Path] = None
    document_filename: Optional[str] = None

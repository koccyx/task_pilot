"""RAG configuration loaded from environment variables."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


class RagSettings(BaseModel):
    """Runtime settings for the RAG web service."""

    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_collection: str = Field(default="internal_documents_bge_m3")
    embedding_provider: str = Field(default="ollama")
    embedding_model: str = Field(default="bge-m3")
    embedding_base_url: str = Field(default="http://localhost:11434")
    embedding_api_key: str = Field(default="")
    embedding_timeout_seconds: float = Field(default=60.0, gt=0)
    embedding_dimension: int = Field(default=1024, ge=32)
    chunk_size: int = Field(default=700, ge=200)
    chunk_overlap: int = Field(default=150, ge=0)

    @classmethod
    def from_env(cls) -> "RagSettings":
        """Create settings from environment variables."""
        return cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_collection=os.getenv(
                "RAG_QDRANT_COLLECTION",
                "internal_documents_bge_m3",
            ),
            embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "ollama"),
            embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "bge-m3"),
            embedding_base_url=os.getenv(
                "RAG_EMBEDDING_BASE_URL",
                "http://localhost:11434",
            ),
            embedding_api_key=os.getenv("RAG_EMBEDDING_API_KEY", ""),
            embedding_timeout_seconds=float(
                os.getenv("RAG_EMBEDDING_TIMEOUT_SECONDS", "60")
            ),
            embedding_dimension=int(os.getenv("RAG_EMBEDDING_DIMENSION", "1024")),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "700")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "150")),
        )

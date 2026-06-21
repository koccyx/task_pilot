"""Qdrant-backed vector storage for RAG chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams


@dataclass(frozen=True)
class VectorSearchResult:
    """One vector search result."""

    chunk_id: str
    document_id: str
    filename: str
    text: str
    score: float


class VectorStore(Protocol):
    """Vector store protocol used by RagService."""

    def ensure_collection(self) -> None:
        """Ensure backing collection exists."""

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Upsert embedded chunks."""

    def search(self, vector: list[float], limit: int = 5) -> list[VectorSearchResult]:
        """Search chunks by vector."""

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """Delete chunk vectors by ids."""


class QdrantVectorStore:
    """Qdrant implementation of VectorStore."""

    def __init__(self, url: str, collection_name: str, vector_size: int) -> None:
        self.client = QdrantClient(url=url, check_compatibility=False)
        self.collection_name = collection_name
        self.vector_size = vector_size

    def ensure_collection(self) -> None:
        """Create collection when it does not exist yet."""
        collections = self.client.get_collections().collections
        existing_names = {collection.name for collection in collections}
        if self.collection_name in existing_names:
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
            ),
        )

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Upsert embedded chunks into Qdrant."""
        self.ensure_collection()
        points = [
            PointStruct(
                id=chunk["chunk_id"],
                vector=chunk["vector"],
                payload={
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "filename": chunk["filename"],
                    "text": chunk["text"],
                },
            )
            for chunk in chunks
        ]
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)

    def search(self, vector: list[float], limit: int = 5) -> list[VectorSearchResult]:
        """Search chunks by vector."""
        self.ensure_collection()
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        results: list[VectorSearchResult] = []
        for hit in response.points:
            payload = hit.payload or {}
            results.append(
                VectorSearchResult(
                    chunk_id=str(payload.get("chunk_id", hit.id)),
                    document_id=str(payload.get("document_id", "")),
                    filename=str(payload.get("filename", "")),
                    text=str(payload.get("text", "")),
                    score=float(hit.score),
                )
            )
        return results

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """Delete chunk vectors by ids."""
        if not chunk_ids:
            return
        self.ensure_collection()
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=chunk_ids),
        )

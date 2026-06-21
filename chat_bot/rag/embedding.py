"""Embedding providers for the internal RAG index."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class TextEmbedder(Protocol):
    """Embedder contract used by RagService."""

    def embed(self, text: str) -> list[float]:
        """Embed a search query."""

    def embed_document(self, text: str) -> list[float]:
        """Embed a document chunk."""


class HashingEmbedding:
    """Small dependency-free hashing embedder.

    This is intentionally local and deterministic. It keeps the RAG feature usable
    without an external embedding provider; the vector store can later be reused with
    stronger embeddings by replacing this class.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        """Embed text into a normalized sparse hashing vector."""
        return self._embed(text)

    def embed_document(self, text: str) -> list[float]:
        """Embed a document chunk into a normalized sparse hashing vector."""
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[\wа-яА-ЯёЁ]+", text.lower())

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            sign = 1.0 if value & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0:
            return vector
        return [item / norm for item in vector]


class OllamaEmbedding:
    """Embedding client backed by a local Ollama server."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        """Embed a search query."""
        return self._embed_batch([text])[0]

    def embed_document(self, text: str) -> list[float]:
        """Embed a document chunk."""
        return self._embed_batch([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks in one HTTP request."""
        if not texts:
            return []
        return self._embed_batch(texts)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        import httpx

        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={
                "model": self.model,
                "input": texts,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        vectors = payload.get("embeddings", [])
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Ollama returned {len(vectors)} embeddings for {len(texts)} inputs"
            )
        return vectors


def build_embedder(
    provider: str,
    dimension: int,
    model: str,
    base_url: str,
    api_key: str,
    timeout_seconds: float,
) -> TextEmbedder:
    """Build embedder from runtime settings."""
    normalized_provider = provider.strip().lower()
    if normalized_provider == "hashing":
        return HashingEmbedding(dimension)
    if normalized_provider == "ollama":
        return OllamaEmbedding(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported RAG embedding provider: {provider}")

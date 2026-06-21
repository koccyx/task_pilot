"""PostgreSQL metadata repository for uploaded RAG documents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol

import asyncpg
from asyncpg import Pool, Record


@dataclass(frozen=True)
class StoredDocument:
    """Metadata for one uploaded document."""

    id: str
    filename: str
    content_type: str
    size_bytes: int
    stored_path: str
    uploaded_at: str


@dataclass(frozen=True)
class StoredChunk:
    """One extracted text chunk."""

    id: str
    document_id: str
    chunk_index: int
    text: str


class RagRepository(Protocol):
    """Repository contract used by RagService."""

    async def add_document(
        self,
        document: StoredDocument,
        chunks: Iterable[StoredChunk],
        content: bytes,
    ) -> None:
        """Store document metadata and chunks atomically."""

    async def list_documents(self) -> list[StoredDocument]:
        """Return documents ordered from newest to oldest."""

    async def get_document(self, document_id: str) -> StoredDocument | None:
        """Return a document by id."""

    async def list_chunks(self, document_id: str) -> list[StoredChunk]:
        """Return chunks for a document."""

    async def get_chunk(self, chunk_id: str) -> StoredChunk | None:
        """Return one chunk by id."""

    async def list_all_chunks(self) -> list[StoredChunk]:
        """Return all chunks for lexical retrieval."""

    async def delete_chunk(self, chunk_id: str) -> bool:
        """Delete one chunk by id."""

    async def delete_document(self, document_id: str) -> bool:
        """Delete one document and its chunks."""

    async def count_chunks(self, document_id: str) -> int:
        """Count chunks for one document."""


class PostgresRagRepository:
    """Persist RAG document metadata and extracted chunks in PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._pool: Optional[Pool] = None
        self._schema_ready = False

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._schema_ready = False

    async def _get_pool(self) -> Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=1,
                max_size=5,
            )
        if not self._schema_ready:
            await self._ensure_schema()
        return self._pool

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        if self._pool is None:
            raise RuntimeError("PostgreSQL pool is not initialized")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    stored_path TEXT NOT NULL,
                    content BYTEA NOT NULL DEFAULT ''::bytea,
                    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES rag_documents(id)
                        ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_id
                ON rag_chunks(document_id);

                CREATE INDEX IF NOT EXISTS idx_rag_documents_uploaded_at
                ON rag_documents(uploaded_at DESC);
                """
            )
            await conn.execute(
                """
                ALTER TABLE rag_documents
                ADD COLUMN IF NOT EXISTS content BYTEA NOT NULL DEFAULT ''::bytea
                """
            )
        self._schema_ready = True

    async def add_document(
        self,
        document: StoredDocument,
        chunks: Iterable[StoredChunk],
        content: bytes,
    ) -> None:
        """Store document metadata and chunks atomically."""
        chunk_rows = [
            (chunk.id, chunk.document_id, chunk.chunk_index, chunk.text)
            for chunk in chunks
        ]
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO rag_documents (
                        id, filename, content_type, size_bytes,
                        stored_path, content, uploaded_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    document.id,
                    document.filename,
                    document.content_type,
                    document.size_bytes,
                    document.stored_path,
                    content,
                    self._parse_timestamp(document.uploaded_at),
                )
                await conn.executemany(
                    """
                    INSERT INTO rag_chunks (id, document_id, chunk_index, text)
                    VALUES ($1, $2, $3, $4)
                    """,
                    chunk_rows,
                )

    async def list_documents(self) -> list[StoredDocument]:
        """Return documents ordered from newest to oldest."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, filename, content_type, size_bytes, stored_path, uploaded_at
                FROM rag_documents
                ORDER BY uploaded_at DESC
                """
            )
        return [self._document_from_record(row) for row in rows]

    async def get_document(self, document_id: str) -> StoredDocument | None:
        """Return a document by id."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, filename, content_type, size_bytes, stored_path, uploaded_at
                FROM rag_documents
                WHERE id = $1
                """,
                document_id,
            )
        return self._document_from_record(row) if row else None

    async def list_chunks(self, document_id: str) -> list[StoredChunk]:
        """Return chunks for a document."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, document_id, chunk_index, text
                FROM rag_chunks
                WHERE document_id = $1
                ORDER BY chunk_index ASC
                """,
                document_id,
            )
        return [self._chunk_from_record(row) for row in rows]

    async def get_chunk(self, chunk_id: str) -> StoredChunk | None:
        """Return one chunk by id."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, document_id, chunk_index, text
                FROM rag_chunks
                WHERE id = $1
                """,
                chunk_id,
            )
        return self._chunk_from_record(row) if row else None

    async def list_all_chunks(self) -> list[StoredChunk]:
        """Return all chunks for lexical retrieval."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, document_id, chunk_index, text
                FROM rag_chunks
                ORDER BY document_id ASC, chunk_index ASC
                """
            )
        return [self._chunk_from_record(row) for row in rows]

    async def delete_chunk(self, chunk_id: str) -> bool:
        """Delete one chunk by id."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM rag_chunks WHERE id = $1",
                chunk_id,
            )
        return result.endswith(" 1")

    async def delete_document(self, document_id: str) -> bool:
        """Delete one document and its chunks."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM rag_documents WHERE id = $1",
                document_id,
            )
        return result.endswith(" 1")

    async def count_chunks(self, document_id: str) -> int:
        """Count chunks for one document."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT COUNT(*) FROM rag_chunks WHERE document_id = $1",
                document_id,
            )
        return int(value or 0)

    @staticmethod
    def now_iso() -> str:
        """Return current timestamp in a stable ISO format."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def from_env() -> "PostgresRagRepository":
        """Create repository from DATABASE_URL."""
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/task_pilot",
        )
        return PostgresRagRepository(database_url=database_url)

    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _timestamp_to_str(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @classmethod
    def _document_from_record(cls, record: Record) -> StoredDocument:
        return StoredDocument(
            id=record["id"],
            filename=record["filename"],
            content_type=record["content_type"],
            size_bytes=record["size_bytes"],
            stored_path=record["stored_path"],
            uploaded_at=cls._timestamp_to_str(record["uploaded_at"]),
        )

    @staticmethod
    def _chunk_from_record(record: Record) -> StoredChunk:
        return StoredChunk(
            id=record["id"],
            document_id=record["document_id"],
            chunk_index=record["chunk_index"],
            text=record["text"],
        )

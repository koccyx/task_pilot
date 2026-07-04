"""Tests for internal RAG ingestion and search."""

from typing import Any

import pytest

from chat_bot.rag.embedding import OllamaEmbedding
from chat_bot.rag.repository import StoredChunk, StoredDocument
from chat_bot.rag.service import RagService
from chat_bot.rag.settings import RagSettings
from chat_bot.rag.vector_store import VectorSearchResult


class InMemoryVectorStore:
    """Simple vector store test double."""

    def __init__(self) -> None:
        self.chunks: list[dict[str, Any]] = []

    def ensure_collection(self) -> None:
        pass

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks.extend(chunks)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        chunk_id_set = set(chunk_ids)
        self.chunks = [
            chunk for chunk in self.chunks if chunk["chunk_id"] not in chunk_id_set
        ]

    def search(self, vector: list[float], limit: int = 5) -> list[VectorSearchResult]:
        scored = []
        for chunk in self.chunks:
            score = sum(left * right for left, right in zip(vector, chunk["vector"]))
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            VectorSearchResult(
                chunk_id=chunk["chunk_id"],
                document_id=chunk["document_id"],
                filename=chunk["filename"],
                text=chunk["text"],
                score=score,
            )
            for score, chunk in scored[:limit]
        ]


class FixedDenseVectorStore(InMemoryVectorStore):
    """Vector store that returns a predefined dense ranking."""

    def __init__(self, results: list[VectorSearchResult]) -> None:
        super().__init__()
        self.results = results

    def search(self, vector: list[float], limit: int = 5) -> list[VectorSearchResult]:
        _ = vector
        return self.results[:limit]


class KeywordReranker:
    """Reranker test double that promotes chunks containing a keyword."""

    def __init__(self, keyword: str) -> None:
        self.keyword = keyword

    def rerank(
        self,
        query: str,
        results: list[VectorSearchResult],
        limit: int,
    ) -> list[VectorSearchResult]:
        _ = query
        ordered = sorted(
            results,
            key=lambda result: self.keyword.lower() in result.text.lower(),
            reverse=True,
        )
        return ordered[:limit]


class InMemoryRagRepository:
    """Async metadata repository test double."""

    def __init__(self) -> None:
        self.documents: dict[str, StoredDocument] = {}
        self.chunks: dict[str, list[StoredChunk]] = {}

    async def add_document(
        self,
        document: StoredDocument,
        chunks: list[StoredChunk],
        content: bytes,
    ) -> None:
        _ = content
        self.documents[document.id] = document
        self.chunks[document.id] = list(chunks)

    async def list_documents(self) -> list[StoredDocument]:
        return list(self.documents.values())

    async def get_document(self, document_id: str) -> StoredDocument | None:
        return self.documents.get(document_id)

    async def list_chunks(self, document_id: str) -> list[StoredChunk]:
        return self.chunks.get(document_id, [])

    async def get_chunk(self, chunk_id: str) -> StoredChunk | None:
        for chunks in self.chunks.values():
            for chunk in chunks:
                if chunk.id == chunk_id:
                    return chunk
        return None

    async def list_all_chunks(self) -> list[StoredChunk]:
        return [
            chunk
            for document_chunks in self.chunks.values()
            for chunk in document_chunks
        ]

    async def delete_chunk(self, chunk_id: str) -> bool:
        for document_id, chunks in self.chunks.items():
            remaining_chunks = [chunk for chunk in chunks if chunk.id != chunk_id]
            if len(remaining_chunks) != len(chunks):
                self.chunks[document_id] = remaining_chunks
                return True
        return False

    async def delete_document(self, document_id: str) -> bool:
        if document_id not in self.documents:
            return False
        del self.documents[document_id]
        self.chunks.pop(document_id, None)
        return True

    async def count_chunks(self, document_id: str) -> int:
        return len(self.chunks.get(document_id, []))


def make_service(tmp_path) -> tuple[RagService, InMemoryVectorStore]:
    vector_store = InMemoryVectorStore()
    service = RagService(
        settings=RagSettings(
            embedding_provider="hashing",
            embedding_dimension=384,
            chunk_size=220,
            chunk_overlap=30,
        ),
        repository=InMemoryRagRepository(),
        vector_store=vector_store,
    )
    return service, vector_store


@pytest.mark.asyncio
async def test_ingest_file_stores_metadata_chunks_and_vectors(tmp_path) -> None:
    service, vector_store = make_service(tmp_path)

    result = await service.ingest_file(
        filename="policy.txt",
        content_type="text/plain",
        content=(
            "Внутренний регламент: задачи заводятся в Kaiten. "
            "Документация хранится в базе знаний."
        ).encode("utf-8"),
    )

    assert result.document.filename == "policy.txt"
    assert result.chunk_count >= 1
    assert len(vector_store.chunks) == result.chunk_count

    documents = await service.list_documents()
    assert [document.filename for document in documents] == ["policy.txt"]

    document, chunks = await service.get_document_with_chunks(result.document.id)
    assert document.id == result.document.id
    assert "Внутренний регламент" in chunks[0].text


@pytest.mark.asyncio
async def test_search_returns_relevant_chunks(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    await service.ingest_file(
        filename="docs.md",
        content_type="text/markdown",
        content="Qdrant хранит векторы документов для RAG поиска.".encode("utf-8"),
    )

    results = await service.search("где хранятся векторы", limit=3)

    assert results
    assert results[0].filename == "docs.md"
    assert "Qdrant" in results[0].text


def test_chunk_text_uses_token_size_and_overlap(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    service.settings.chunk_size = 5
    service.settings.chunk_overlap = 2
    text = " ".join(f"token{i}" for i in range(12))

    chunks = service.chunk_text(text)

    assert chunks == [
        "token0 token1 token2 token3 token4",
        "token3 token4 token5 token6 token7",
        "token6 token7 token8 token9 token10",
        "token9 token10 token11",
    ]


@pytest.mark.asyncio
async def test_search_fuses_dense_and_bm25_with_rrf(tmp_path) -> None:
    _ = tmp_path
    repository = InMemoryRagRepository()
    target_document = StoredDocument(
        id="target-doc",
        filename="policy.txt",
        content_type="text/plain",
        size_bytes=10,
        stored_path="postgres://rag_documents.content",
        uploaded_at="2026-06-21T00:00:00+00:00",
    )
    noise_document = StoredDocument(
        id="noise-doc",
        filename="noise.txt",
        content_type="text/plain",
        size_bytes=10,
        stored_path="postgres://rag_documents.content",
        uploaded_at="2026-06-21T00:00:00+00:00",
    )
    target_chunk = StoredChunk(
        id="target-chunk",
        document_id=target_document.id,
        chunk_index=0,
        text="Политикаотпусков описывает правила согласования отпусков.",
    )
    noise_chunk = StoredChunk(
        id="noise-chunk",
        document_id=noise_document.id,
        chunk_index=0,
        text="Этот фрагмент про случайные заметки без нужного термина.",
    )
    await repository.add_document(target_document, [target_chunk], b"target")
    await repository.add_document(noise_document, [noise_chunk], b"noise")

    vector_store = FixedDenseVectorStore(
        [
            VectorSearchResult(
                chunk_id=noise_chunk.id,
                document_id=noise_document.id,
                filename=noise_document.filename,
                text=noise_chunk.text,
                score=0.99,
            ),
            VectorSearchResult(
                chunk_id=target_chunk.id,
                document_id=target_document.id,
                filename=target_document.filename,
                text=target_chunk.text,
                score=0.10,
            ),
        ]
    )
    service = RagService(
        settings=RagSettings(embedding_provider="hashing", embedding_dimension=384),
        repository=repository,
        vector_store=vector_store,
    )

    results = await service.search("политикаотпусков", limit=2)

    assert [result.chunk_id for result in results] == [
        target_chunk.id,
        noise_chunk.id,
    ]
    assert results[0].filename == "policy.txt"


@pytest.mark.asyncio
async def test_search_applies_reranker_after_rrf(tmp_path) -> None:
    _ = tmp_path
    repository = InMemoryRagRepository()
    document = StoredDocument(
        id="doc",
        filename="policy.txt",
        content_type="text/plain",
        size_bytes=10,
        stored_path="postgres://rag_documents.content",
        uploaded_at="2026-06-21T00:00:00+00:00",
    )
    first_chunk = StoredChunk(
        id="first-chunk",
        document_id=document.id,
        chunk_index=0,
        text="Общий регламент без итогового маркера.",
    )
    promoted_chunk = StoredChunk(
        id="promoted-chunk",
        document_id=document.id,
        chunk_index=1,
        text="Этот фрагмент содержит marker и должен стать первым после rerank.",
    )
    await repository.add_document(document, [first_chunk, promoted_chunk], b"content")

    vector_store = FixedDenseVectorStore(
        [
            VectorSearchResult(
                chunk_id=first_chunk.id,
                document_id=document.id,
                filename=document.filename,
                text=first_chunk.text,
                score=0.99,
            ),
            VectorSearchResult(
                chunk_id=promoted_chunk.id,
                document_id=document.id,
                filename=document.filename,
                text=promoted_chunk.text,
                score=0.10,
            ),
        ]
    )
    service = RagService(
        settings=RagSettings(embedding_provider="hashing", embedding_dimension=384),
        repository=repository,
        vector_store=vector_store,
        reranker=KeywordReranker("marker"),
    )

    results = await service.search("регламент", limit=1)

    assert [result.chunk_id for result in results] == [promoted_chunk.id]


@pytest.mark.asyncio
async def test_delete_document_removes_metadata_chunks_and_vectors(tmp_path) -> None:
    service, vector_store = make_service(tmp_path)
    result = await service.ingest_file(
        filename="delete-me.txt",
        content_type="text/plain",
        content="Документ для удаления из базы знаний.".encode("utf-8"),
    )

    deleted = await service.delete_document(result.document.id)

    assert deleted is True
    assert await service.list_documents() == []
    assert await service.repository.list_all_chunks() == []
    assert vector_store.chunks == []


@pytest.mark.asyncio
async def test_delete_chunk_removes_chunk_and_vector(tmp_path) -> None:
    service, vector_store = make_service(tmp_path)
    result = await service.ingest_file(
        filename="chunk-delete.txt",
        content_type="text/plain",
        content=(
            "Первый фрагмент документа достаточно длинный. "
            "Второй фрагмент документа тоже достаточно длинный. "
            "Третий фрагмент документа завершает текст."
        ).encode("utf-8"),
    )
    _, chunks = await service.get_document_with_chunks(result.document.id)
    chunk_to_delete = chunks[0]

    deleted_chunk = await service.delete_chunk(chunk_to_delete.id)

    assert deleted_chunk == chunk_to_delete
    _, remaining_chunks = await service.get_document_with_chunks(result.document.id)
    assert chunk_to_delete.id not in {chunk.id for chunk in remaining_chunks}
    assert chunk_to_delete.id not in {
        chunk["chunk_id"] for chunk in vector_store.chunks
    }


def test_ollama_embedding_uses_embed_endpoint(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    embedder = OllamaEmbedding(
        base_url="http://host.docker.internal:11434/",
        model="bge-m3",
        timeout_seconds=15,
    )

    vectors = embedder.embed_documents(["первый", "второй"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "http://host.docker.internal:11434/api/embed"
    assert captured["json"] == {
        "model": "bge-m3",
        "input": ["первый", "второй"],
    }
    assert captured["timeout"] == 15

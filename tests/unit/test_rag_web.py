"""Tests for the RAG web interface."""

from fastapi.testclient import TestClient

from chat_bot.rag.service import RagService
from chat_bot.rag.settings import RagSettings
from chat_bot.rag.web import _format_moscow_time, create_app
from tests.unit.test_rag_service import InMemoryRagRepository, InMemoryVectorStore


def test_web_upload_lists_and_shows_document(tmp_path) -> None:
    _ = tmp_path
    service = RagService(
        settings=RagSettings(embedding_provider="hashing", embedding_dimension=384),
        repository=InMemoryRagRepository(),
        vector_store=InMemoryVectorStore(),
    )
    client = TestClient(create_app(service))

    upload_response = client.post(
        "/upload",
        files={"file": ("manual.txt", b"Internal manual content", "text/plain")},
        follow_redirects=False,
    )

    assert upload_response.status_code == 303

    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "manual.txt" in index_response.text
    assert "Загруженные файлы" in index_response.text
    assert "МСК" in index_response.text
    assert 'class="table-scroll"' in index_response.text

    document = next(iter(service.repository.documents.values()))
    document_response = client.get(f"/documents/{document.id}")
    assert document_response.status_code == 200
    assert "Internal manual content" in document_response.text
    assert "Загружен:" in document_response.text
    assert "МСК" in document_response.text


def test_web_search_displays_results(tmp_path) -> None:
    _ = tmp_path
    service = RagService(
        settings=RagSettings(embedding_provider="hashing", embedding_dimension=384),
        repository=InMemoryRagRepository(),
        vector_store=InMemoryVectorStore(),
    )
    import asyncio

    asyncio.run(
        service.ingest_file(
            filename="search.txt",
            content_type="text/plain",
            content="Qdrant индексирует внутренние документы.".encode("utf-8"),
        )
    )
    client = TestClient(create_app(service))

    response = client.post("/search", data={"query": "внутренние документы"})

    assert response.status_code == 200
    assert "Результаты поиска" in response.text
    assert "search.txt" in response.text


def test_web_deletes_document(tmp_path) -> None:
    _ = tmp_path
    service = RagService(
        settings=RagSettings(embedding_provider="hashing", embedding_dimension=384),
        repository=InMemoryRagRepository(),
        vector_store=InMemoryVectorStore(),
    )
    import asyncio

    result = asyncio.run(
        service.ingest_file(
            filename="delete.txt",
            content_type="text/plain",
            content="Документ для удаления.".encode("utf-8"),
        )
    )
    client = TestClient(create_app(service))

    response = client.post(
        f"/documents/{result.document.id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert service.repository.documents == {}
    assert service.vector_store.chunks == []


def test_web_deletes_chunk(tmp_path) -> None:
    _ = tmp_path
    service = RagService(
        settings=RagSettings(
            embedding_provider="hashing",
            embedding_dimension=384,
            chunk_size=200,
            chunk_overlap=20,
        ),
        repository=InMemoryRagRepository(),
        vector_store=InMemoryVectorStore(),
    )
    import asyncio

    result = asyncio.run(
        service.ingest_file(
            filename="chunks.txt",
            content_type="text/plain",
            content=(
                "Первый длинный фрагмент для проверки удаления отдельного чанка. " * 12
                + "Второй длинный фрагмент для проверки удаления отдельного чанка. "
                * 12
            ).encode("utf-8"),
        )
    )
    _, chunks = asyncio.run(service.get_document_with_chunks(result.document.id))
    chunk = chunks[0]
    client = TestClient(create_app(service))

    response = client.post(
        f"/documents/{result.document.id}/chunks/{chunk.id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    _, remaining_chunks = asyncio.run(
        service.get_document_with_chunks(result.document.id)
    )
    assert chunk.id not in {remaining_chunk.id for remaining_chunk in remaining_chunks}
    assert chunk.id not in {point["chunk_id"] for point in service.vector_store.chunks}


def test_format_moscow_time_converts_utc_iso_timestamp() -> None:
    assert _format_moscow_time("2026-06-21T10:15:00+00:00") == ("21.06.2026 13:15 МСК")

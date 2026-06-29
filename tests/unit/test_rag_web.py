"""Tests for the RAG web interface."""

from fastapi.testclient import TestClient

from chat_bot.models import UserProfile
from chat_bot.rag.service import RagService
from chat_bot.rag.settings import RagSettings
from chat_bot.rag.web import _format_moscow_time, create_app
from tests.unit.test_rag_service import InMemoryRagRepository, InMemoryVectorStore


class InMemoryUserAdminRepository:
    def __init__(self) -> None:
        self.profiles: dict[tuple[int, int], UserProfile] = {}

    async def upsert_user_profile(self, profile: UserProfile) -> UserProfile:
        key = (profile.chat_id, profile.telegram_user_id)
        self.profiles[key] = profile
        return profile

    async def list_all_user_profiles(self) -> list[UserProfile]:
        return sorted(
            self.profiles.values(),
            key=lambda profile: (profile.chat_id, profile.introduced_name),
        )

    async def set_user_admin(
        self,
        chat_id: int,
        telegram_user_id: int,
        is_admin: bool,
    ) -> UserProfile | None:
        key = (chat_id, telegram_user_id)
        profile = self.profiles.get(key)
        if profile is None:
            return None
        updated = profile.model_copy(update={"is_admin": is_admin})
        self.profiles[key] = updated
        return updated

    async def delete_user_profile(self, chat_id: int, telegram_user_id: int) -> bool:
        return self.profiles.pop((chat_id, telegram_user_id), None) is not None


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


def test_users_page_creates_admin_user() -> None:
    service = RagService(
        settings=RagSettings(embedding_provider="hashing", embedding_dimension=384),
        repository=InMemoryRagRepository(),
        vector_store=InMemoryVectorStore(),
    )
    user_repository = InMemoryUserAdminRepository()
    client = TestClient(create_app(service, user_repository=user_repository))

    response = client.post(
        "/users",
        data={
            "chat_id": "100",
            "telegram_user_id": "200",
            "telegram_username": "stepan",
            "telegram_display_name": "Stepan",
            "introduced_name": "Степан",
            "kaiten_user_name": "Степан Федоров",
            "kaiten_user_id": "300",
            "is_admin": "on",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    profile = user_repository.profiles[(100, 200)]
    assert profile.is_admin is True
    assert profile.kaiten_user_id == 300

    page = client.get("/users")
    assert page.status_code == 200
    assert "Степан" in page.text
    assert "Админ" in page.text
    assert "Пользователи" in page.text


def test_users_page_updates_admin_flag_and_deletes_user() -> None:
    service = RagService(
        settings=RagSettings(embedding_provider="hashing", embedding_dimension=384),
        repository=InMemoryRagRepository(),
        vector_store=InMemoryVectorStore(),
    )
    user_repository = InMemoryUserAdminRepository()
    user_repository.profiles[(100, 200)] = UserProfile(
        chat_id=100,
        telegram_user_id=200,
        telegram_username="stepan",
        telegram_display_name="Stepan",
        introduced_name="Степан",
        is_admin=True,
    )
    client = TestClient(create_app(service, user_repository=user_repository))

    demote_response = client.post(
        "/users/100/200/admin",
        data={},
        follow_redirects=False,
    )

    assert demote_response.status_code == 303
    assert user_repository.profiles[(100, 200)].is_admin is False

    delete_response = client.post(
        "/users/100/200/delete",
        follow_redirects=False,
    )

    assert delete_response.status_code == 303
    assert user_repository.profiles == {}

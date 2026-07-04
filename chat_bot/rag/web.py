"""FastAPI web interface for internal documentation RAG."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated, Protocol
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from chat_bot.models import PostgresConfig, UserProfile
from chat_bot.repository_postgres import ChatRepository

from .service import RagService
from .settings import RagSettings


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    """Return shared RAG service instance."""
    return RagService(RagSettings.from_env())


class UserAdminRepository(Protocol):
    """Repository contract used by the RAG web user admin UI."""

    async def upsert_user_profile(self, profile: UserProfile) -> UserProfile:
        """Create or update a user profile."""

    async def list_all_user_profiles(self) -> list[UserProfile]:
        """Return all known user profiles."""

    async def set_user_admin(
        self,
        chat_id: int,
        telegram_user_id: int,
        is_admin: bool,
    ) -> UserProfile | None:
        """Set admin flag for one profile."""

    async def delete_user_profile(self, chat_id: int, telegram_user_id: int) -> bool:
        """Delete one profile."""


@lru_cache(maxsize=1)
def get_user_repository() -> ChatRepository:
    """Return shared user repository backed by PostgreSQL."""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/task_pilot",
    )
    return ChatRepository(PostgresConfig(database_url=database_url))


def create_app(
    service: RagService | None = None,
    user_repository: UserAdminRepository | None = None,
) -> FastAPI:
    """Create the RAG web application."""
    app = FastAPI(title="Task Pilot RAG", version="1.0.0")

    def service_instance() -> RagService:
        return service or get_rag_service()

    def user_repository_instance() -> UserAdminRepository:
        return user_repository or get_user_repository()

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        rag_service = service_instance()
        documents = await rag_service.list_documents()
        return _page(
            title="Внутренняя база знаний",
            body=_upload_form()
            + _search_form()
            + await _document_list(rag_service, documents),
        )

    @app.get("/users", response_class=HTMLResponse)
    async def users_page() -> str:
        profiles = await user_repository_instance().list_all_user_profiles()
        return _page(
            title="Пользователи",
            body=_user_form() + _user_list(profiles),
            active="users",
            subtitle=(
                "Управление Telegram-профилями, соответствием Kaiten и "
                "админскими правами Task Pilot."
            ),
        )

    @app.post("/users")
    async def upsert_user(
        chat_id: Annotated[int, Form(...)],
        telegram_user_id: Annotated[int, Form(...)],
        telegram_display_name: Annotated[str, Form(...)],
        introduced_name: Annotated[str, Form(...)],
        telegram_username: Annotated[str, Form()] = "",
        kaiten_user_name: Annotated[str, Form()] = "",
        kaiten_user_id: Annotated[str, Form()] = "",
        is_admin: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        profile = _build_user_profile(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            telegram_display_name=telegram_display_name,
            introduced_name=introduced_name,
            kaiten_user_name=kaiten_user_name,
            kaiten_user_id=kaiten_user_id,
            is_admin=is_admin == "on",
        )
        repository = user_repository_instance()
        await repository.upsert_user_profile(profile)
        updated = await repository.set_user_admin(
            chat_id=profile.chat_id,
            telegram_user_id=profile.telegram_user_id,
            is_admin=profile.is_admin,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return RedirectResponse("/users", status_code=303)

    @app.post("/users/{chat_id}/{telegram_user_id}/admin")
    async def set_user_admin(
        chat_id: int,
        telegram_user_id: int,
        is_admin: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        updated = await user_repository_instance().set_user_admin(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            is_admin=is_admin == "on",
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return RedirectResponse("/users", status_code=303)

    @app.post("/users/{chat_id}/{telegram_user_id}/delete")
    async def delete_user(chat_id: int, telegram_user_id: int) -> RedirectResponse:
        deleted = await user_repository_instance().delete_user_profile(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return RedirectResponse("/users", status_code=303)

    @app.post("/upload")
    async def upload(file: Annotated[UploadFile, File(...)]) -> RedirectResponse:
        rag_service = service_instance()
        content = await file.read()
        try:
            await rag_service.ingest_file(
                filename=file.filename or "document",
                content_type=file.content_type or "application/octet-stream",
                content=content,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse("/", status_code=303)

    @app.get("/documents/{document_id}", response_class=HTMLResponse)
    async def document_page(document_id: str) -> str:
        rag_service = service_instance()
        try:
            document, chunks = await rag_service.get_document_with_chunks(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Файл не найден") from exc

        body = (
            '<p><a href="/">← Назад к списку</a></p>'
            f"<section><h2>{html.escape(document.filename)}</h2>"
            f"<p class='muted'>Загружен: {html.escape(_format_moscow_time(document.uploaded_at))} · "
            f"чанков: {len(chunks)}</p>"
            f"<form action='/documents/{document.id}/delete' method='post'>"
            "<button class='danger' type='submit'>Удалить документ</button>"
            "</form></section>"
            "<section><h3>Содержимое</h3>"
            + "".join(
                "<article class='chunk'>"
                "<div class='chunk-header'>"
                f"<div class='muted'>Чанк {chunk.chunk_index + 1}</div>"
                f"<form action='/documents/{document.id}/chunks/{chunk.id}/delete' method='post'>"
                "<button class='danger secondary' type='submit'>Удалить чанк</button>"
                "</form>"
                "</div>"
                f"<pre>{html.escape(chunk.text)}</pre>"
                "</article>"
                for chunk in chunks
            )
            + "</section>"
        )
        return _page(title=document.filename, body=body)

    @app.post("/documents/{document_id}/delete")
    async def delete_document(document_id: str) -> RedirectResponse:
        rag_service = service_instance()
        deleted = await rag_service.delete_document(document_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Файл не найден")
        return RedirectResponse("/", status_code=303)

    @app.post("/documents/{document_id}/chunks/{chunk_id}/delete")
    async def delete_chunk(document_id: str, chunk_id: str) -> RedirectResponse:
        rag_service = service_instance()
        try:
            _, chunks = await rag_service.get_document_with_chunks(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Файл не найден") from exc
        if not any(chunk.id == chunk_id for chunk in chunks):
            raise HTTPException(status_code=404, detail="Чанк не найден")
        chunk = await rag_service.delete_chunk(chunk_id)
        if chunk is None:
            raise HTTPException(status_code=404, detail="Чанк не найден")
        return RedirectResponse(f"/documents/{document_id}", status_code=303)

    @app.post("/search", response_class=HTMLResponse)
    async def search(query: Annotated[str, Form(...)]) -> str:
        rag_service = service_instance()
        results = await rag_service.search(query, limit=8)
        body = (
            '<p><a href="/">← Назад к списку</a></p>'
            + _search_form(query)
            + "<section><h2>Результаты поиска</h2>"
            + (
                "".join(
                    "<article class='result'>"
                    f"<h3>{html.escape(result.filename)}</h3>"
                    f"<p class='muted'>score: {result.score:.4f}</p>"
                    f"<pre>{html.escape(result.text)}</pre>"
                    "</article>"
                    for result in results
                )
                if results
                else "<p class='muted'>Ничего не найдено.</p>"
            )
            + "</section>"
        )
        return _page(title="Поиск", body=body)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "rag-web"}

    return app


def _page(
    title: str,
    body: str,
    active: str = "documents",
    subtitle: str = "Загрузка документов, просмотр содержимого и поиск по Qdrant.",
) -> str:
    documents_active = "active" if active == "documents" else ""
    users_active = "active" if active == "users" else ""
    return f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #697586;
      --line: #d7dde5;
      --accent: #2563eb;
      --accent-dark: #1d4ed8;
      --success: #16a34a;
      --warning: #d97706;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      width: min(1040px, calc(100vw - 32px));
      margin: 32px auto;
    }}
    header {{ margin-bottom: 20px; }}
    h1 {{ margin: 0 0 6px; font-size: 28px; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; }}
    section, article {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 16px;
    }}
    form {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    .nav {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .nav a {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font-weight: 600;
    }}
    .nav a.active {{
      border-color: var(--accent);
      background: #eff6ff;
      color: var(--accent-dark);
    }}
    input[type="file"], input[type="text"] {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 10px;
      min-height: 40px;
    }}
    input[type="text"] {{ min-width: min(520px, 100%); flex: 1; }}
    input[type="number"] {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 10px;
      min-height: 40px;
      width: 180px;
    }}
    label.checkbox {{
      display: inline-flex;
      align-items: center;
      min-height: 40px;
      gap: 8px;
      font-weight: 600;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      min-height: 40px;
      padding: 0 14px;
      font-weight: 600;
      cursor: pointer;
    }}
    button:hover {{ background: var(--accent-dark); }}
    button.danger {{ background: #dc2626; }}
    button.danger:hover {{ background: #b91c1c; }}
    button.success {{ background: var(--success); }}
    button.success:hover {{ background: #15803d; }}
    button.secondary {{ min-height: 32px; padding: 0 10px; font-size: 12px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      min-height: 24px;
      padding: 0 9px;
      font-size: 12px;
      font-weight: 700;
      background: #f3f4f6;
      color: #374151;
    }}
    .badge.admin {{ background: #fef3c7; color: #92400e; }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(180px, 1fr));
      gap: 12px;
      width: 100%;
      align-items: end;
    }}
    .field {{ display: grid; gap: 6px; }}
    .field span {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }}
    .field input {{ width: 100%; min-width: 0; }}
    .table-scroll {{ width: 100%; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-size: 13px; font-weight: 600; }}
    td.actions {{ width: 1%; white-space: nowrap; }}
    td.actions form {{ justify-content: flex-end; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      line-height: 1.45;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
    }}
    .muted {{ color: var(--muted); }}
    .chunk, .result {{ padding: 14px; }}
    .chunk-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 1040px); margin: 20px auto; }}
      section, article {{ padding: 14px; }}
      .table-scroll {{ overflow-x: visible; }}
      table, thead, tbody, tr, th, td {{ display: block; }}
      thead {{ display: none; }}
      tr {{
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 10px;
      }}
      td {{
        display: grid;
        grid-template-columns: minmax(88px, 34%) minmax(0, 1fr);
        gap: 10px;
        border-bottom: 0;
        padding: 7px 0;
        overflow-wrap: anywhere;
      }}
      td::before {{
        content: attr(data-label);
        color: var(--muted);
        font-size: 13px;
        font-weight: 600;
      }}
      td.actions {{
        width: auto;
        white-space: normal;
        grid-template-columns: 1fr;
      }}
      td.actions::before {{ content: ""; display: none; }}
      td.actions form, td.actions button {{ width: 100%; }}
      .chunk-header {{ align-items: flex-start; flex-direction: column; }}
      .chunk-header form, .chunk-header button {{ width: 100%; }}
      .form-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(title)}</h1>
      <p class="muted">{html.escape(subtitle)}</p>
      <nav class="nav">
        <a class="{documents_active}" href="/">Документы RAG</a>
        <a class="{users_active}" href="/users">Пользователи</a>
      </nav>
    </header>
    {body}
  </main>
</body>
</html>
"""


def _build_user_profile(
    chat_id: int,
    telegram_user_id: int,
    telegram_username: str,
    telegram_display_name: str,
    introduced_name: str,
    kaiten_user_name: str,
    kaiten_user_id: str,
    is_admin: bool,
) -> UserProfile:
    try:
        parsed_kaiten_user_id = int(kaiten_user_id) if kaiten_user_id.strip() else None
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Kaiten ID должен быть числом",
        ) from exc

    try:
        return UserProfile(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username or None,
            telegram_display_name=telegram_display_name,
            introduced_name=introduced_name,
            kaiten_user_name=kaiten_user_name or None,
            kaiten_user_id=parsed_kaiten_user_id,
            is_admin=is_admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _user_form() -> str:
    return """
<section>
  <h2>Добавить или обновить пользователя</h2>
  <form action="/users" method="post">
    <div class="form-grid">
      <label class="field">
        <span>Chat ID</span>
        <input type="number" name="chat_id" required>
      </label>
      <label class="field">
        <span>Telegram user ID</span>
        <input type="number" name="telegram_user_id" required>
      </label>
      <label class="field">
        <span>Telegram username</span>
        <input type="text" name="telegram_username" placeholder="username без @">
      </label>
      <label class="field">
        <span>Имя в Telegram</span>
        <input type="text" name="telegram_display_name" required>
      </label>
      <label class="field">
        <span>Имя для бота</span>
        <input type="text" name="introduced_name" required>
      </label>
      <label class="field">
        <span>Имя в Kaiten</span>
        <input type="text" name="kaiten_user_name">
      </label>
      <label class="field">
        <span>Kaiten user ID</span>
        <input type="number" name="kaiten_user_id">
      </label>
      <label class="checkbox">
        <input type="checkbox" name="is_admin">
        Админ
      </label>
      <button class="success" type="submit">Сохранить</button>
    </div>
  </form>
</section>
"""


def _user_list(profiles: list[UserProfile]) -> str:
    if not profiles:
        rows = (
            "<tr><td colspan='8' class='muted'>Пользователи пока не заведены.</td></tr>"
        )
    else:
        rendered_rows = []
        for profile in profiles:
            username = (
                f"@{profile.telegram_username}" if profile.telegram_username else ""
            )
            admin_badge = (
                "<span class='badge admin'>Админ</span>"
                if profile.is_admin
                else "<span class='badge'>Пользователь</span>"
            )
            checked = " checked" if profile.is_admin else ""
            kaiten = profile.kaiten_user_name or ""
            if profile.kaiten_user_id:
                kaiten = f"{kaiten} ({profile.kaiten_user_id})".strip()
            rendered_rows.append(
                "<tr>"
                f"<td data-label='Chat ID'>{profile.chat_id}</td>"
                f"<td data-label='Telegram ID'>{profile.telegram_user_id}</td>"
                f"<td data-label='Username'>{html.escape(username)}</td>"
                f"<td data-label='Имя'>{html.escape(profile.introduced_name)}</td>"
                f"<td data-label='Kaiten'>{html.escape(kaiten)}</td>"
                f"<td data-label='Права'>{admin_badge}</td>"
                "<td class='actions' data-label='Админ'>"
                f"<form action='/users/{profile.chat_id}/{profile.telegram_user_id}/admin' method='post'>"
                f"<label class='checkbox'><input type='checkbox' name='is_admin'{checked}> Админ</label>"
                "<button class='secondary' type='submit'>Применить</button>"
                "</form>"
                "</td>"
                "<td class='actions' data-label='Удалить'>"
                f"<form action='/users/{profile.chat_id}/{profile.telegram_user_id}/delete' method='post'>"
                "<button class='danger secondary' type='submit'>Удалить</button>"
                "</form>"
                "</td>"
                "</tr>"
            )
        rows = "".join(rendered_rows)

    return f"""
<section>
  <h2>Пользователи</h2>
  <div class="table-scroll">
  <table>
    <thead>
      <tr>
        <th>Chat ID</th>
        <th>Telegram ID</th>
        <th>Username</th>
        <th>Имя</th>
        <th>Kaiten</th>
        <th>Права</th>
        <th>Админ</th>
        <th></th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
</section>
"""


def _upload_form() -> str:
    return """
<section>
  <h2>Загрузить файл</h2>
  <form action="/upload" method="post" enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Загрузить</button>
  </form>
</section>
"""


def _search_form(query: str = "") -> str:
    return f"""
<section>
  <h2>Поиск</h2>
  <form action="/search" method="post">
    <input type="text" name="query" value="{html.escape(query)}"
           placeholder="Введите вопрос или ключевые слова" required>
    <button type="submit">Искать</button>
  </form>
</section>
"""


async def _document_list(service: RagService, documents: list) -> str:
    if not documents:
        rows = "<tr><td colspan='4' class='muted'>Файлы пока не загружены.</td></tr>"
    else:
        rendered_rows = []
        for document in documents:
            chunk_count = await service.chunk_count(document.id)
            rendered_rows.append(
                "<tr>"
                f"<td data-label='Файл'><a href='/documents/{document.id}'>{html.escape(document.filename)}</a></td>"
                f"<td data-label='Чанки'>{chunk_count}</td>"
                f"<td data-label='Загружен'>{html.escape(_format_moscow_time(document.uploaded_at))}</td>"
                "<td class='actions' data-label='Действие'>"
                f"<form action='/documents/{document.id}/delete' method='post'>"
                "<button class='danger secondary' type='submit'>Удалить</button>"
                "</form>"
                "</td>"
                "</tr>"
            )
        rows = "".join(rendered_rows)

    return f"""
<section>
  <h2>Загруженные файлы</h2>
  <div class="table-scroll">
  <table>
    <thead>
      <tr>
        <th>Файл</th>
        <th>Чанки</th>
        <th>Загружен</th>
        <th></th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
</section>
"""


def _format_moscow_time(timestamp: str) -> str:
    """Format an ISO timestamp in Moscow time for the web UI."""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    moscow_time = parsed.astimezone(ZoneInfo("Europe/Moscow"))
    return moscow_time.strftime("%d.%m.%Y %H:%M МСК")


app = create_app()


def main() -> None:
    """Run the RAG web interface."""
    uvicorn.run(
        "chat_bot.rag.web:app",
        host="0.0.0.0",
        port=int(__import__("os").environ.get("RAG_WEB_PORT", "8090")),
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()

"""FastAPI web interface for internal documentation RAG."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from .service import RagService
from .settings import RagSettings


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    """Return shared RAG service instance."""
    return RagService(RagSettings.from_env())


def create_app(service: RagService | None = None) -> FastAPI:
    """Create the RAG web application."""
    app = FastAPI(title="Task Pilot RAG", version="1.0.0")

    def service_instance() -> RagService:
        return service or get_rag_service()

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
            f"{document.size_bytes} байт · чанков: {len(chunks)}</p>"
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


def _page(title: str, body: str) -> str:
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
    input[type="file"], input[type="text"] {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 10px;
      min-height: 40px;
    }}
    input[type="text"] {{ min-width: min(520px, 100%); flex: 1; }}
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
    button.secondary {{ min-height: 32px; padding: 0 10px; font-size: 12px; }}
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
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(title)}</h1>
      <p class="muted">Загрузка документов, просмотр содержимого и поиск по Qdrant.</p>
    </header>
    {body}
  </main>
</body>
</html>
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
        rows = "<tr><td colspan='6' class='muted'>Файлы пока не загружены.</td></tr>"
    else:
        rendered_rows = []
        for document in documents:
            chunk_count = await service.chunk_count(document.id)
            rendered_rows.append(
                "<tr>"
                f"<td data-label='Файл'><a href='/documents/{document.id}'>{html.escape(document.filename)}</a></td>"
                f"<td data-label='Тип'>{html.escape(document.content_type)}</td>"
                f"<td data-label='Размер'>{document.size_bytes}</td>"
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
        <th>Тип</th>
        <th>Размер</th>
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

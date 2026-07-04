# task_pilot

Агент Task-Pilot

## Запуск

1. Скопируйте `env.example` в `.env` и заполните:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_BOT_USERNAME`
   - `AI_API_KEY`
   - `AI_MODEL`
   - `AI_LIGHT_MODEL` — опциональная легкая модель для роутинга, RAG gate и коротких сводок; по умолчанию в `env.example` используется Ollama `qwen3:8b`
   - `KAITEN_API_URL`
   - `KAITEN_API_TOKEN`
   - при необходимости поменяйте `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Запустите MCP сервер:

```bash
python -m chat_bot.mcp_server.server
```

4. Запустите Telegram-бота:

```bash
python -m chat_bot.bot
```

## Docker Compose

```bash
docker compose up --build
```

При запуске через `docker compose` дополнительно поднимается `PostgreSQL`:
- PostgreSQL: `localhost:5432`
- история чатов сохраняется в таблицу `chat_messages`
- профили представления пользователей сохраняются в таблицу `user_profiles`

RAG-сервисы `qdrant` и `rag-web` запускаются отдельно через profile `embeddings`;
эмбеддинги запрашиваются у локальной Ollama на хосте.
Легкая LLM для роутинга тоже может работать через локальную Ollama:

```bash
ollama pull qwen3:8b
```

```bash
ollama pull bge-m3
```

Docker-запуск RAG:

```bash
docker compose --profile embeddings up --build postgres qdrant rag-web
```

Настройки задаются через переменные:

```text
QDRANT_URL=http://localhost:6333
RAG_QDRANT_COLLECTION=internal_documents_bge_m3
RAG_WEB_PORT=8090
RAG_EMBEDDING_PROVIDER=ollama
RAG_EMBEDDING_MODEL=bge-m3
RAG_EMBEDDING_BASE_URL=http://localhost:11434
RAG_EMBEDDING_DIMENSION=1024
RAG_RERANKER_ENABLED=true
RAG_RERANKER_PROVIDER=lexical
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=150
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/task_pilot
```

`RAG_CHUNK_SIZE` и `RAG_CHUNK_OVERLAP` задаются в whitespace-токенах.
После dense search, BM25 и RRF включается финальный reranker.

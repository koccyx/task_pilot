# task_pilot

Простой Telegram-агент для создания и обновления задач в Kaiten через MCP.
История чатов и профили пользователей теперь хранятся в `PostgreSQL`.

В проекте осталось:
- `chat_bot.bot` — основной Telegram-бот
- `chat_bot.assistant` — один LLM-агент для natural language запросов
- `chat_bot.mcp_server` — MCP сервер с инструментами Kaiten

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

Перед первой нормальной работой пользователь должен представиться:

```text
/introduce name="Имя Фамилия" kaiten="Имя в Kaiten" kaiten_id=123
```

Параметры `kaiten` и `kaiten_id` необязательны, но без них агент не будет
угадывать соответствие пользователя в Kaiten.

## Архитектура

```text
Telegram -> MessageRouter -> MCPHandler -> SimpleTaskAgent -> Kaiten task tools
```

Агент получает последние 10 сообщений диалога и текущий запрос. Он может создавать
карточки, формировать описания из контекста, назначать исполнителей и перемещать
карточки в указанную колонку. Агенту доступны только task-инструменты Kaiten.

## RAG для внутренней документации

В проект добавлен отдельный веб-интерфейс для внутренней базы знаний:

```bash
python -m chat_bot.rag.web
```

По умолчанию веб-интерфейс доступен на `http://localhost:8090`.
Через него можно:
- загрузить файл;
- посмотреть список загруженных файлов;
- открыть извлеченное содержимое файла;
- удалить документ или отдельный чанк;
- выполнить поиск по загруженным документам.

Тексты документов режутся на чанки, метаданные и извлеченное содержимое
сохраняются в PostgreSQL, а векторы индексируются в Qdrant. Для эмбеддингов
используется `bge-m3` через локальную Ollama на хосте.
Поиск гибридный: dense retrieval по cosine similarity в Qdrant объединяется с
BM25 по текстам чанков через Reciprocal Rank Fusion.

Перед запуском RAG подтяните модель в Ollama на Mac:

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
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=150
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/task_pilot
```

`RAG_CHUNK_SIZE` и `RAG_CHUNK_OVERLAP` задаются в whitespace-токенах.

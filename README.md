# task_pilot

Упрощённый проект: один Telegram-агент, который работает только с Kaiten через MCP.
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
При запуске через `docker compose` дополнительно поднимается `PostgreSQL`:
- PostgreSQL: `localhost:5432`
- история чатов сохраняется в таблицу `chat_messages`
- профили представления пользователей сохраняются в таблицу `user_profiles`

Перед первой нормальной работой пользователь должен представиться:

```text
/introduce name="Имя Фамилия" kaiten="Имя в Kaiten"
```

Параметр `kaiten` необязателен.

## Архитектура

```text
Telegram -> chat_bot.bot -> MessageRouter -> MCPHandler -> Assistant -> Kaiten MCP tools
```

# Docker

Проект запускается с тремя основными сервисами:
- `postgres`
- `mcp-server`
- `telegram-bot`

## Запуск

```bash
docker compose up --build
```

## Storage

Для хранения истории чатов и профилей пользователей используется `PostgreSQL`.

- PostgreSQL: `localhost:5432`
- Доступы задаются через `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- Таблицы `chat_messages` и `user_profiles` создаются автоматически при первом подключении

## Эндпоинты

- MCP: `http://localhost:8000/mcp`
- Bot healthcheck: `http://localhost:8080/health`

# Быстрый старт: Логирование в Grafana

## Шаг 1: Установка зависимостей

```bash
pip install python-json-logger python-logging-loki
```

Или с uv:

```bash
uv pip install python-json-logger python-logging-loki
```

## Шаг 2: Запуск Grafana + Loki

```bash
docker-compose -f docker-compose.grafana.yml up -d
```

Проверьте, что сервисы запущены:

```bash
docker-compose -f docker-compose.grafana.yml ps
```

## Шаг 3: Настройка переменных окружения

Добавьте в `.env`:

```bash
# Уровень логирования
LOG_LEVEL=INFO

# Использовать JSON формат (обязательно для Loki)
LOG_JSON=true

# URL Loki для отправки логов
LOKI_URL=http://localhost:3100/loki/api/v1/push
```

## Шаг 4: Запуск приложения

Запустите MCP сервер или бота как обычно:

```bash
# MCP Server
uv run python -m chat_bot.mcp_server.server

# Telegram Bot
uv run python -m chat_bot.bot
```

## Шаг 5: Просмотр логов в Grafana

1. Откройте http://localhost:3000
2. Логин: `admin`, Пароль: `admin`
3. Перейдите в **Explore** → выберите источник данных **Loki**
4. Введите запрос: `{service="task_pilot-mcp-server"}`
5. Нажмите **Run query**

## Предустановленный дашборд

После первого запуска Grafana автоматически загрузит дашборд **"task_pilot - Logs Dashboard"** с панелями:

- 📊 Логи по уровням
- 📝 Последние логи
- ⏱️ Время выполнения методов
- ❌ Частота ошибок
- 📈 Вызовы методов во времени

## Примеры запросов LogQL

### Все логи
```
{service="task_pilot-mcp-server"}
```

### Только ошибки
```
{service="task_pilot-mcp-server", level="ERROR"}
```

### Логи конкретного метода
```
{service="task_pilot-mcp-server"} |= "manage_cards"
```

### Методы с временем выполнения > 1 секунды
```
{service="task_pilot-mcp-server"} |= "Method completed" | json | duration_ms > 1000
```

## Устранение проблем

### Логи не появляются в Grafana

1. Проверьте, что Loki запущен:
   ```bash
   curl http://localhost:3100/ready
   ```

2. Проверьте переменную `LOKI_URL` в `.env`

3. Проверьте логи приложения - они должны быть в JSON формате

### Promtail не собирает логи

Проверьте логи Promtail:
```bash
docker logs promtail
```

## Дополнительная информация

Полная документация: [docs/LOGGING.md](docs/LOGGING.md)

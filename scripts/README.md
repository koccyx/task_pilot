# Скрипты для тестирования MCP

Этот каталог содержит скрипты для проверки основных вызовов MCP инструментов.

## Быстрая проверка MCP вызовов

### test_mcp_basic.py

Простые тесты основных вызовов MCP инструментов через HTTP транспорт (MCP Inspector подход).

**Использование:**

```bash
# Убедитесь, что MCP сервер запущен
python -m chat_bot.mcp_server.server

# В другом терминале запустите тесты
python scripts/test_mcp_basic.py
```

**Переменные окружения:**

- `MCP_SERVER_URL` - URL MCP сервера (по умолчанию: `http://localhost:8000/mcp`)
- `KAITEN_API_URL` - URL Kaiten API (должен быть настроен)
- `KAITEN_API_TOKEN` - токен Kaiten API (должен быть настроен)

**Что проверяется:**

- Подключение к MCP серверу
- `manage_users` - список пользователей
- `manage_spaces` - список пространств
- `manage_boards` - список досок
- `manage_columns` - список колонок
- `manage_cards` - список карточек
- `manage_sprints` - список спринтов
- `move_card` - перемещение карточки (проверка обработки ошибок)

### test_mcp_inspector.sh

Обертка для запуска `test_mcp_basic.py` через bash скрипт.

```bash
./scripts/test_mcp_inspector.sh
```

## Интеграционные тесты через pytest

Для более детального тестирования используйте pytest:

```bash
# Запуск всех интеграционных тестов
pytest -m integration

# Запуск конкретного файла
pytest tests/integration/test_mcp_calls.py -v
```

## Требования

1. **MCP сервер должен быть запущен:**
   ```bash
   python -m chat_bot.mcp_server.server
   ```

2. **Настроены переменные окружения:**
   ```bash
   export KAITEN_API_URL=https://koccyx.kaiten.ru/api/latest/
   export KAITEN_API_TOKEN=your_token_here
   export MCP_SERVER_URL=http://localhost:8000/mcp  # опционально
   ```

3. **Установлены зависимости:**
   ```bash
   pip install -r requirements.txt
   ```

## Примеры использования

### Быстрая проверка работоспособности

```bash
# 1. Запустите MCP сервер в одном терминале
python -m chat_bot.mcp_server.server

# 2. В другом терминале запустите тесты
python scripts/test_mcp_basic.py
```

### Проверка с кастомным URL

```bash
export MCP_SERVER_URL=http://example.com:8000/mcp
python scripts/test_mcp_basic.py
```

### Запуск через pytest с подробным выводом

```bash
pytest tests/integration/test_mcp_calls.py -v -s
```

## Устранение проблем

### Ошибка подключения к серверу

```
❌ Failed to connect to MCP server
```

**Решение:**
1. Убедитесь, что MCP сервер запущен
2. Проверьте URL сервера: `echo $MCP_SERVER_URL`
3. Проверьте доступность: `curl http://localhost:8000/mcp`

### Ошибки аутентификации Kaiten API

Если тесты падают с ошибками API, проверьте:
1. Правильность `KAITEN_API_URL`
2. Валидность `KAITEN_API_TOKEN`
3. Доступность Kaiten API из вашей сети

### Таймауты

Если тесты падают по таймауту, увеличьте значение в скрипте:
```python
config = MCPClientConfig(server_url=MCP_SERVER_URL, timeout=60.0)  # увеличьте до 60 или больше
```

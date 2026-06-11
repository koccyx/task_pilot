# Тестирование проекта

Этот документ описывает структуру тестов и способы их запуска.

## Структура тестов

```
tests/
├── __init__.py
├── conftest.py              # Общие фикстуры pytest
├── README.md                # Этот файл
├── unit/                    # Unit тесты
│   ├── __init__.py
│   ├── test_command_parser.py    # Тесты парсера команд
│   ├── test_command_registry.py  # Тесты реестра команд
│   ├── test_command_handler.py    # Тесты обработчика команд
│   └── test_models.py            # Тесты Pydantic моделей
└── integration/             # Интеграционные тесты (MCP Inspector)
    ├── __init__.py
    └── test_mcp_calls.py    # Тесты вызовов MCP инструментов через HTTP
```

## Установка зависимостей

Перед запуском тестов установите зависимости:

```bash
# С помощью pip
pip install -r requirements.txt

# Или с помощью uv
uv sync --extra mcp --extra bot
```

## Запуск тестов

### Запуск всех тестов

```bash
pytest
```

### Запуск с подробным выводом

```bash
pytest -v
```

### Запуск конкретного файла тестов

```bash
# Тесты парсера команд
pytest tests/unit/test_command_parser.py

# Тесты реестра команд
pytest tests/unit/test_command_registry.py

# Тесты обработчика команд
pytest tests/unit/test_command_handler.py

# Тесты моделей
pytest tests/unit/test_models.py
```

### Запуск конкретного теста

```bash
pytest tests/unit/test_command_parser.py::TestCommandParser::test_parse_simple_command
```

### Запуск с покрытием кода

```bash
# Терминальный отчет
pytest --cov=chat_bot --cov-report=term-missing

# HTML отчет
pytest --cov=chat_bot --cov-report=html
# Откройте htmlcov/index.html в браузере

# XML отчет (для CI/CD)
pytest --cov=chat_bot --cov-report=xml
```

### Запуск только unit тестов

```bash
pytest -m unit
```

### Запуск интеграционных тестов (MCP Inspector)

**Важно:** Перед запуском интеграционных тестов убедитесь, что MCP сервер запущен:

```bash
# В одном терминале запустите MCP сервер
python -m chat_bot.mcp_server.server

# В другом терминале запустите тесты
pytest -m integration
```

Или используйте быстрый скрипт для проверки основных вызовов:

```bash
# Использование Python скрипта
python scripts/test_mcp_basic.py

# Или bash скрипт
./scripts/test_mcp_inspector.sh
```

### Запуск в параллельном режиме (требует pytest-xdist)

```bash
pip install pytest-xdist
pytest -n auto
```

## Что тестируется

### CommandParser (`test_command_parser.py`)

- ✅ Определение команд (текст начинается с `/`)
- ✅ Парсинг простых команд без аргументов
- ✅ Парсинг команд с одним и несколькими аргументами
- ✅ Обработка кавычек (одинарных и двойных)
- ✅ Автоматическое определение типов (int, float, bool, str)
- ✅ Обработка неизвестных команд
- ✅ Обработка команд с упоминанием бота (@botname)
- ✅ Обработка специальных символов в значениях

### CommandRegistry (`test_command_registry.py`)

- ✅ Инициализация реестра команд
- ✅ Получение информации о командах
- ✅ Форматирование справки
- ✅ Валидация структуры команд
- ✅ Проверка наличия основных команд

### CommandHandler (`test_command_handler.py`)

- ✅ Обработка различных типов команд
- ✅ Обработка ошибок (отсутствие MCP сервера, неверные параметры)
- ✅ Инициализация MCP клиента
- ✅ Вызов MCP инструментов
- ✅ Обработка команд с параметрами и без

### Models (`test_models.py`)

- ✅ Валидация Pydantic моделей
- ✅ Обработка обязательных и опциональных полей
- ✅ Валидация типов данных
- ✅ Проверка значений по умолчанию

### Integration Tests - MCP Calls (`test_mcp_calls.py`)

Интеграционные тесты для проверки основных вызовов MCP инструментов через HTTP транспорт (MCP Inspector подход):

- ✅ Подключение к MCP серверу
- ✅ Вызов `manage_users` (list)
- ✅ Вызов `manage_spaces` (list)
- ✅ Вызов `manage_boards` (list)
- ✅ Вызов `manage_cards` (list)
- ✅ Вызов `manage_columns` (list)
- ✅ Вызов `move_card` (структура и обработка ошибок)

**Требования:**
- MCP сервер должен быть запущен на `http://localhost:8000` (или URL из `MCP_SERVER_URL`)
- Настроены переменные окружения: `KAITEN_API_URL`, `KAITEN_API_TOKEN`

## Фикстуры

В `conftest.py` определены общие фикстуры:

- `mock_repository` - мок репозитория для тестирования
- `sample_message` - пример сообщения
- `sample_messages_data` - пример данных сообщений
- `sample_command_request` - пример запроса команды
- `event_loop` - event loop для async тестов

## Написание новых тестов

При добавлении нового функционала создавайте соответствующие тесты:

1. **Unit тесты** - для изолированных функций и классов
2. **Моки** - используйте `unittest.mock` для внешних зависимостей
3. **Async тесты** - используйте `@pytest.mark.asyncio` для async функций

### Пример unit теста

```python
import pytest
from chat_bot.commands.parser import CommandParser
from chat_bot.models import CommandType

def test_parse_command():
    """Test parsing a command."""
    result = CommandParser.parse(
        "/create_task title=Test",
        chat_id=123,
        user_id=456
    )
    assert result.command_type == CommandType.CREATE_TASK
    assert result.arguments == {"title": "Test"}
```

### Пример async теста

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_async_function():
    """Test an async function."""
    mock_obj = MagicMock()
    mock_obj.method = AsyncMock(return_value="result")
    
    result = await mock_obj.method()
    assert result == "result"
```

## Проверка покрытия кода

Минимальное покрытие установлено в `pytest.ini` на 70%. 

Для просмотра детального отчета:

```bash
pytest --cov=chat_bot --cov-report=html
open htmlcov/index.html  # macOS
```

## Интеграция в CI/CD

Пример конфигурации для GitHub Actions:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest --cov=chat_bot --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

## Устранение проблем

### Ошибка "No module named pytest"

Установите зависимости:
```bash
pip install -r requirements.txt
```

### Ошибка импорта модулей

Убедитесь, что вы находитесь в корневой директории проекта:
```bash
cd /path/to/task_pilot
pytest
```

### Ошибки с async тестами

Убедитесь, что установлен `pytest-asyncio`:
```bash
pip install pytest-asyncio
```

### Тесты не находят модули

Проверьте, что структура проекта правильная и все `__init__.py` файлы на месте.

# Руководство по тестированию

## Обзор

В проект добавлена полная структура тестирования с использованием pytest. Тесты покрывают основные компоненты системы: парсер команд, реестр команд, обработчик команд и модели данных.

## Что было добавлено

### 1. Зависимости для тестирования

В `requirements.txt` добавлены:
- `pytest>=8.0.0` - фреймворк для тестирования
- `pytest-asyncio>=0.23.0` - поддержка async тестов
- `pytest-mock>=3.12.0` - улучшенные моки
- `pytest-cov>=4.1.0` - покрытие кода

### 2. Структура тестов

```
tests/
├── __init__.py
├── conftest.py                    # Общие фикстуры
├── README.md                      # Подробная документация
├── unit/                          # Unit тесты
│   ├── __init__.py
│   ├── test_command_parser.py    # 18 тестов
│   ├── test_command_registry.py  # 9 тестов
│   ├── test_command_handler.py   # 15 тестов
│   └── test_models.py            # 12 тестов
└── integration/                   # Интеграционные тесты (MCP Inspector)
    ├── __init__.py
    └── test_mcp_calls.py         # 8 тестов основных MCP вызовов

scripts/
├── test_mcp_basic.py             # Скрипт для быстрой проверки MCP вызовов
└── test_mcp_inspector.sh         # Bash обертка для test_mcp_basic.py
```

### 3. Конфигурация pytest

Создан `pytest.ini` с настройками:
- Автоматическое обнаружение тестов
- Поддержка async тестов
- Маркеры для категоризации тестов
- Настройки логирования

## Какие тесты добавлены

### CommandParser (18 тестов)

Тестирует парсинг slash-команд:
- ✅ Определение команд (текст начинается с `/`)
- ✅ Парсинг простых команд без аргументов
- ✅ Парсинг команд с одним и несколькими аргументами
- ✅ Обработка кавычек (одинарных и двойных)
- ✅ Автоматическое определение типов (int, float, bool, str)
- ✅ Обработка неизвестных команд
- ✅ Обработка команд с упоминанием бота (@botname)
- ✅ Обработка специальных символов в значениях
- ✅ Case-insensitive команды

### CommandRegistry (9 тестов)

Тестирует реестр команд:
- ✅ Инициализация реестра
- ✅ Получение информации о командах
- ✅ Форматирование справки
- ✅ Валидация структуры команд
- ✅ Проверка наличия основных команд

### CommandHandler (15 тестов)

Тестирует обработчик команд:
- ✅ Обработка различных типов команд
- ✅ Обработка ошибок (отсутствие MCP сервера)
- ✅ Инициализация MCP клиента
- ✅ Вызов MCP инструментов
- ✅ Валидация параметров команд
- ✅ Обработка команд с параметрами и без

### Models (12 тестов)

Тестирует Pydantic модели:
- ✅ Валидация CommandRequest
- ✅ Валидация Message
- ✅ Валидация MessagesData
- ✅ Валидация CommandType enum
- ✅ Обработка обязательных и опциональных полей

**Всего: 54 unit теста + 8 интеграционных тестов MCP = 62 теста**

## Как запустить тесты

### 1. Установка зависимостей

```bash
# С помощью pip
pip install -r requirements.txt

# Или с помощью uv
uv sync --extra mcp --extra bot
```

### 2. Базовый запуск

```bash
# Запустить все тесты
pytest

# С подробным выводом
pytest -v

# Запустить конкретный файл
pytest tests/unit/test_command_parser.py
```

### 3. Запуск с покрытием кода

```bash
# Терминальный отчет
pytest --cov=chat_bot --cov-report=term-missing

# HTML отчет (откроется в браузере)
pytest --cov=chat_bot --cov-report=html
open htmlcov/index.html  # macOS
```

### 4. Запуск конкретных тестов

```bash
# Конкретный тест
pytest tests/unit/test_command_parser.py::TestCommandParser::test_parse_simple_command

# Все тесты класса
pytest tests/unit/test_command_parser.py::TestCommandParser

# Тесты по маркеру
pytest -m unit                    # Только unit тесты
pytest -m integration             # Только интеграционные тесты (требует запущенного MCP сервера)
```

### 5. Запуск интеграционных тестов MCP (MCP Inspector подход)

**Важно:** Перед запуском интеграционных тестов MCP сервер должен быть запущен.

```bash
# В одном терминале запустите MCP сервер
python -m chat_bot.mcp_server.server

# В другом терминале запустите тесты
pytest -m integration

# Или используйте быстрый скрипт для проверки основных вызовов
python scripts/test_mcp_basic.py

# Или через bash скрипт
./scripts/test_mcp_inspector.sh
```

**Интеграционные тесты проверяют:**
- ✅ Подключение к MCP серверу через HTTP
- ✅ Вызов `manage_users` (list)
- ✅ Вызов `manage_spaces` (list)
- ✅ Вызов `manage_boards` (list)
- ✅ Вызов `manage_cards` (list)
- ✅ Вызов `manage_sprints` (list)
- ✅ Вызов `manage_columns` (list)
- ✅ Вызов `move_card` (структура и обработка ошибок)
- ✅ Вызов `sprint_summary` (структура)

**Требования для интеграционных тестов:**
- MCP сервер должен быть запущен (`python -m chat_bot.mcp_server.server`)
- Настроены переменные окружения: `KAITEN_API_URL`, `KAITEN_API_TOKEN`

## Проверка работы

После установки зависимостей выполните:

```bash
# 1. Проверить, что pytest установлен
pytest --version

# 2. Запустить все тесты
pytest -v

# 3. Проверить покрытие
pytest --cov=chat_bot --cov-report=term-missing
```

Ожидаемый результат:
- Все тесты должны пройти успешно
- Покрытие кода должно быть > 70% для протестированных модулей

## Структура тестов

### Фикстуры (conftest.py)

- `mock_repository` - мок репозитория для тестирования
- `sample_message` - пример сообщения
- `sample_messages_data` - пример данных сообщений
- `sample_command_request` - пример запроса команды
- `event_loop` - event loop для async тестов

### Примеры использования фикстур

```python
def test_with_fixture(sample_message):
    """Использование фикстуры в тесте."""
    assert sample_message.message_id == 1

@pytest.mark.asyncio
async def test_async_with_mock(mock_repository):
    """Использование мока в async тесте."""
    result = await mock_repository.read_chat_messages(123)
    assert result is not None
```

## Написание новых тестов

При добавлении нового функционала:

1. Создайте файл `test_<module_name>.py` в `tests/unit/`
2. Импортируйте необходимые модули
3. Используйте фикстуры из `conftest.py`
4. Для async функций используйте `@pytest.mark.asyncio`
5. Для моков используйте `unittest.mock`

Пример:

```python
import pytest
from chat_bot.your_module import YourClass

class TestYourClass:
    def test_something(self):
        obj = YourClass()
        assert obj.method() == expected_result

    @pytest.mark.asyncio
    async def test_async_method(self):
        obj = YourClass()
        result = await obj.async_method()
        assert result is not None
```

## Интеграция в CI/CD

Пример для GitHub Actions:

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
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest --cov=chat_bot --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Дополнительная информация

Подробная документация находится в:
- `tests/README.md` - детальное описание тестов
- `README.md` - раздел "Тестирование"
- `pytest.ini` - конфигурация pytest

## Устранение проблем

### Ошибка "No module named pytest"
```bash
pip install -r requirements.txt
```

### Ошибки импорта
Убедитесь, что вы в корневой директории проекта:
```bash
cd /path/to/task_pilot
pytest
```

### Проблемы с async тестами
Убедитесь, что установлен `pytest-asyncio`:
```bash
pip install pytest-asyncio
```

## Интеграционные тесты MCP (MCP Inspector)

Добавлены интеграционные тесты для проверки основных вызовов MCP инструментов через HTTP транспорт.

### Быстрая проверка

```bash
# 1. Запустите MCP сервер
python -m chat_bot.mcp_server.server

# 2. В другом терминале запустите тесты
python scripts/test_mcp_basic.py
```

Подробная документация: `scripts/README.md`

## Следующие шаги

Для расширения тестового покрытия рекомендуется:

1. ✅ Добавить интеграционные тесты для MCP сервера (выполнено)
2. Добавить тесты для других обработчиков (MCPHandler, Router)
3. Добавить тесты для клиентов (KaitenClient)
4. Добавить тесты для утилит и вспомогательных функций
5. Настроить автоматический запуск тестов в CI/CD

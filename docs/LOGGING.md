# Логирование в Grafana

Проект использует структурированное JSON-логирование для интеграции с Grafana Loki. Все логи автоматически отправляются в Loki и могут быть визуализированы в Grafana.

## Что логируется

### 1. Входные параметры и вызываемый метод

Каждый вызов метода логируется с:
- Именем метода (полный путь: `module.function_name`)
- Входными параметрами (автоматически санитизируются, скрываются токены/пароли)
- Временной меткой

Пример:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "method_name": "chat_bot.mcp_server.tools.manage_cards.manage_cards",
  "input_params": {
    "action": "create",
    "title": "Новая задача",
    "board": "Sprint 5"
  },
  "message": "Method called"
}
```

### 2. Промежуточные вызовы методов

Все промежуточные вызовы методов логируются с:
- Именем метода
- Входными параметрами
- Результатами работы
- Временем выполнения (в миллисекундах)

Пример:
```json
{
  "timestamp": "2024-01-15T10:30:01Z",
  "level": "DEBUG",
  "method_name": "find_board_by_name",
  "input_params": {
    "board_name": "Sprint 5"
  },
  "duration_ms": 45.2,
  "message": "Intermediate method call completed"
}
```

### 3. Общий результат работы

После завершения метода логируется:
- Имя метода
- Результат работы (усеченный для больших объектов)
- Время выполнения
- Статус (успех/ошибка)

Пример:
```json
{
  "timestamp": "2024-01-15T10:30:02Z",
  "level": "INFO",
  "method_name": "chat_bot.mcp_server.tools.manage_cards.manage_cards",
  "result": {
    "content": [{"type": "text", "text": "Card created with ID: 12345"}],
    "meta": {"operation": "create", "card_id": 12345}
  },
  "duration_ms": 234.5,
  "message": "Method completed"
}
```

### 4. Бизнес-ошибки и исключения

Все ошибки логируются с:
- Типом ошибки
- Сообщением об ошибке
- Полным traceback
- Временем выполнения до ошибки

Пример:
```json
{
  "timestamp": "2024-01-15T10:30:03Z",
  "level": "ERROR",
  "method_name": "chat_bot.mcp_server.tools.manage_cards._resolve_board_id",
  "error_type": "ValueError",
  "error_message": "Board not found: Invalid Board",
  "traceback": "Traceback (most recent call last):\n  ...",
  "duration_ms": 12.3,
  "message": "Method failed"
}
```

## Развертывание Grafana + Loki

### Быстрый старт с Docker Compose

1. **Запустите Grafana и Loki:**

```bash
docker-compose -f docker-compose.grafana.yml up -d
```

2. **Проверьте, что сервисы запущены:**

```bash
docker-compose -f docker-compose.grafana.yml ps
```

Должны быть запущены:
- `loki` на порту 3100
- `grafana` на порту 3000
- `promtail` (опционально, для файловых логов)

3. **Откройте Grafana:**

- URL: http://localhost:3000
- Логин: `admin`
- Пароль: `admin`

4. **Настройте источник данных Loki:**

Источник данных Loki уже настроен автоматически через provisioning. Если нужно настроить вручную:

1. Перейдите в **Configuration → Data Sources**
2. Нажмите **Add data source**
3. Выберите **Loki**
4. URL: `http://loki:3100` (внутри Docker) или `http://localhost:3100` (снаружи)
5. Нажмите **Save & Test**

### Настройка приложения для отправки логов в Loki

#### Вариант 1: Прямая отправка в Loki (рекомендуется)

Установите переменную окружения:

```bash
export LOKI_URL=http://localhost:3100/loki/api/v1/push
```

Или добавьте в `.env`:

```bash
LOKI_URL=http://localhost:3100/loki/api/v1/push
```

**Требования:**
- Установите `python-logging-loki`: `pip install python-logging-loki`

#### Вариант 2: Через Promtail (для файловых логов)

1. Настройте вывод логов в файл:

```python
# В вашем коде
import logging
file_handler = logging.FileHandler('/var/log/app/app.log')
logger.addHandler(file_handler)
```

2. Promtail автоматически соберет логи из `/var/log/app/` и отправит в Loki.

### Настройка переменных окружения

Добавьте в `.env`:

```bash
# Уровень логирования
LOG_LEVEL=INFO

# Использовать JSON формат (обязательно для Loki)
LOG_JSON=true

# URL Loki для прямой отправки (опционально)
LOKI_URL=http://localhost:3100/loki/api/v1/push
```

## Использование в коде

### Автоматическое логирование методов

Используйте декоратор `@log_method_call`:

```python
from chat_bot.logging_config import log_method_call, get_logger

logger = get_logger(__name__)

@log_method_call(log_input=True, log_output=True, log_errors=True)
async def my_function(param1: str, param2: int) -> dict:
    """My function with automatic logging."""
    # Ваш код
    return {"result": "success"}
```

### Логирование промежуточных вызовов

Используйте контекстный менеджер `log_intermediate_call`:

```python
from chat_bot.logging_config import log_intermediate_call, get_logger

logger = get_logger(__name__)

async def my_function():
    with log_intermediate_call(logger, "external_api_call", endpoint="/api/data"):
        result = await call_external_api()
    return result
```

### Ручное логирование

```python
from chat_bot.logging_config import get_logger

logger = get_logger(__name__)

logger.info(
    "Custom log message",
    extra={
        "method_name": "my_function",
        "input_params": {"param1": "value1"},
        "custom_field": "custom_value",
    },
)
```

## Дашборды Grafana

### Предустановленный дашборд

После запуска Grafana автоматически загружается дашборд "task_pilot - Logs Dashboard" с панелями:

1. **Logs by Level** - количество логов по уровням
2. **Recent Logs** - последние логи с фильтрацией
3. **Method Calls Over Time** - график вызовов методов во времени
4. **Error Rate** - частота ошибок
5. **Method Duration** - время выполнения методов
6. **Errors by Type** - распределение ошибок по типам

### Создание собственных запросов

#### Все логи за последний час:

```logql
{service="task_pilot-mcp-server"}
```

#### Логи конкретного метода:

```logql
{service="task_pilot-mcp-server"} |= "manage_cards"
```

#### Только ошибки:

```logql
{service="task_pilot-mcp-server", level="ERROR"}
```

#### Методы с временем выполнения > 1 секунды:

```logql
{service="task_pilot-mcp-server"} |= "Method completed" | json | duration_ms > 1000
```

#### Ошибки конкретного типа:

```logql
{service="task_pilot-mcp-server", level="ERROR"} | json | error_type="ValueError"
```

## Безопасность

### Автоматическая санитизация

Система автоматически скрывает чувствительные данные:
- Поля с `token`, `password`, `secret`, `key`, `auth` в названии заменяются на `***REDACTED***`
- Длинные строки усекаются до 1000 символов
- Большие списки ограничиваются первыми 10 элементами

### Рекомендации

1. **Не логируйте токены и пароли** - они автоматически скрываются, но лучше не передавать их в логи
2. **Используйте контекстные переменные** для передачи служебной информации
3. **Ограничивайте размер логов** - большие объекты автоматически усекаются

## Устранение проблем

### Логи не появляются в Grafana

1. Проверьте, что Loki запущен:
   ```bash
   curl http://localhost:3100/ready
   ```

2. Проверьте подключение к Loki:
   ```bash
   curl http://localhost:3100/loki/api/v1/labels
   ```

3. Проверьте логи приложения - они должны быть в JSON формате

4. Проверьте переменную `LOKI_URL` в `.env`

### Promtail не собирает логи

1. Проверьте, что путь к логам правильный в `promtail-config.yml`
2. Проверьте, что файлы логов доступны для чтения
3. Проверьте логи Promtail:
   ```bash
   docker logs promtail
   ```

### Высокое потребление памяти

1. Настройте retention политику в Loki
2. Используйте фильтрацию логов (не логируйте все на DEBUG)
3. Ограничьте размер логов через `max_length` параметр

## Дополнительные ресурсы

- [Документация Loki](https://grafana.com/docs/loki/latest/)
- [Документация Grafana](https://grafana.com/docs/grafana/latest/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)


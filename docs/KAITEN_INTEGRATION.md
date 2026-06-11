# Kaiten Integration Guide

This document describes the hybrid interaction model for managing Kaiten tasks through the Telegram bot.

## Overview

The bot supports two interaction modes for task management:

1. **Natural Language** - Mention the bot and describe what you need
2. **Slash Commands** - Use structured commands with parameters

Both modes route to the same underlying tools and produce consistent results.

## Natural Language Interaction

Mention the bot using `@botusername` and describe your request in natural language.

### Examples

**Creating tasks:**
```
@kaitenbot создай задачу "Подготовить отчет Q4" для Алексея до понедельника
@kaitenbot create task "Design landing page" for Maria due Friday
```

**Listing tasks:**
```
@kaitenbot какие задачи на этой неделе?
@kaitenbot покажи задачи на доске Marketing
```

**Assigning tasks:**
```
@kaitenbot назначь задачу 143 на Ивана
@kaitenbot assign task 143 to Ivan
```

**Board status:**
```
@kaitenbot статус доски Development
@kaitenbot summarize the Marketing board
```

**Creating tasks from discussion:**
```
@kaitenbot создай задачи из нашего обсуждения
@kaitenbot extract tasks from our chat
```

## Slash Commands

Use structured commands for precise control.

### Command Reference

| Command | Parameters | Description |
|---------|------------|-------------|
| `/create_task` | `title`, `assignee`, `due`, `board` | Create a new task |
| `/assign_task` | `id`, `assignee` | Assign a task to someone |
| `/list_tasks` | `board`, `status`, `assignee`, `limit` | List tasks with filters |
| `/board_status` | `board` | Show board summary |
| `/tasks_from_chat` | `days`, `limit` | Extract tasks from chat |
| `/summary` | - | Summarize today's messages |
| `/tasks` | - | Extract tasks from today |
| `/help` | - | Show help message |

### Parameter Syntax

Parameters use `key=value` format. Quoted values support spaces:

```
/create_task title="Prepare Q4 report" assignee=Alex due=2025-12-09
/list_tasks board=Marketing status=in_progress limit=10
/assign_task id=143 assignee="Ivan Petrov"
```

### Status Values

For `/list_tasks status=...`:
- `todo` - Not started
- `in_progress` - Currently in progress
- `done` - Completed
- `blocked` - Blocked by dependency

## Task Extraction from Discussion

When you ask the bot to "create tasks from our discussion", it:

1. Loads recent chat messages from chat storage
2. Analyzes messages using AI to extract actionable items
3. Presents extracted tasks for confirmation
4. Creates confirmed tasks in Kaiten

### Configuring History Range

Use the `/tasks_from_chat` command to specify the time range:

```
/tasks_from_chat days=2        # Last 2 days
/tasks_from_chat limit=100     # Last 100 messages
/tasks_from_chat days=3 limit=50
```

### Confirmation Flow

When multiple tasks are extracted, the bot presents them with confirmation buttons:

```
📋 Найдены задачи для создания:

1. **Подготовить отчет** → Алексей (до 09.12.2025)
2. **Дизайн лендинга** → Мария
3. **Код ревью PR #42** → Иван

Всего: 3 задач

[✅ Создать все] [❌ Отменить]
```

## Intent Classification

The bot uses AI to classify natural language requests into intents:

| Intent | Description | Trigger Examples |
|--------|-------------|------------------|
| `create_task` | Create new task | "создай задачу", "new task", "добавь" |
| `assign_task` | Assign task | "назначь", "assign", "передай" |
| `list_tasks` | Show tasks | "покажи задачи", "какие задачи", "list" |
| `get_board_status` | Board summary | "статус доски", "board status" |
| `create_from_discussion` | Extract from chat | "из обсуждения", "from chat" |
| `summarize` | Message summary | "сводка", "summary" |

## MCP Integration (Future)

The current implementation uses stub tools that return mock data. When the MCP server is available:

1. Tool stubs in `chat_bot/kaiten/tools/` will be replaced with MCP client calls
2. The `chat_bot/mcp/` module provides the template for integration
3. No changes to the user-facing interface will be required

### MCP Tool Mapping

| Current Stub | MCP Tool |
|--------------|----------|
| `CreateTaskTool` | `kaiten_create_task` |
| `AssignTaskTool` | `kaiten_assign_task` |
| `ListTasksTool` | `kaiten_list_tasks` |
| `GetBoardStatusTool` | `kaiten_get_board_status` |

## Configuration

Add these environment variables for Kaiten integration:

```bash
# Kaiten API (stubs for now)
KAITEN_API_URL=https://kaiten.ru/api/v1
KAITEN_API_KEY=your_api_key

# Hybrid mode
HYBRID_MODE_ENABLED=true
TELEGRAM_BOT_USERNAME=your_bot_username

# Task extraction
TASK_EXTRACTION_DEFAULT_DAYS=1
TASK_EXTRACTION_MAX_MESSAGES=100
```

## Error Handling

The bot provides helpful error messages in Russian:

- Missing parameters: "❓ Какую задачу создать? Укажите название."
- Unknown intent: "🤔 Не совсем понял запрос. Попробуйте..."
- Tool errors: "❌ Ошибка: [error message]"

## Security Considerations

1. Bot only responds when directly mentioned or replied to
2. Confirmations have expiration time (30 minutes by default)
3. Only the user who initiated a confirmation can approve/cancel
4. API keys are stored securely and never exposed

## Troubleshooting

### Bot doesn't respond to mentions

1. Check `HYBRID_MODE_ENABLED=true` in environment
2. Verify `TELEGRAM_BOT_USERNAME` matches your bot
3. Ensure bot has permissions to read messages in the chat

### Intent classification is incorrect

1. Be more specific in your request
2. Use keywords like "создай задачу" or "list tasks"
3. Try slash commands for precise control

### Tasks not being created

1. Check Kaiten API configuration (currently uses stubs)
2. Verify task parameters are complete
3. Check bot logs for error details

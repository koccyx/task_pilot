# task_pilot MCP Server

MCP server for working with Kaiten boards, cards, comments, members, tags and time logs.

## Active Tools

- `manage_spaces`
- `manage_boards`
- `manage_columns`
- `manage_cards`
- `manage_comments`
- `manage_members`
- `manage_tags`
- `manage_time_logs`
- `manage_users`
- `move_card`
- `mass_update`
- `auto_archive`
- `break_into_tasks`

## Run

```bash
python -m chat_bot.mcp_server.server
```

Or with `uv`:

```bash
cd chat_bot/mcp_server
uv run python server.py
```

## Required Env Vars

- `KAITEN_API_URL`
- `KAITEN_API_TOKEN`

Optional:

- `HOST` default `0.0.0.0`
- `PORT` default `8000`

## Notes

- Tool schemas are exposed by FastMCP at runtime.
- Name-to-ID resolution is supported for many entities such as spaces, boards, columns and users.

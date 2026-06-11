# Сценарий: Отчёт → Карточка

**Триггер**: "занеси отчёт в кайтен", "создай карточку с отчётом"

**Шаги**:
1. Извлечь: board, title, assignee, report_text, status (готово/в работе/тестирование)
2. `manage_cards(action="create", board="...", title="...")`
3. `manage_members(action="set_responsible", card_id=..., owner_name="...")`
4. `manage_comments(action="add", card_id=..., text="📋 Отчёт:\n...")`
5. `move_card(card_id=..., board="...", column="Готово/В работе/На тестировании")`

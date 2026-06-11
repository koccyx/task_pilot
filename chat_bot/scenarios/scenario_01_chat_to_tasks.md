# Сценарий: Текст → Задачи

**Триггер**: "создай задачи из...", "разбей на задачи"

**Шаги (выполняются последовательно в одном ответе)**:
1. Определить доску (спросить если не указана)
2. Извлечь задачи: title, assignee (@Имя, Имя:), due_date, priority (срочно→urgent)
3. Для каждой задачи — последовательно вызвать:
   - `manage_cards(action="create", board="...", title="...", due_date="...", asap=true/false)` → получить card_id
   - `manage_members(action="set_responsible", card_id=..., owner_name="...")`
   - `manage_tags(action="create", card_id=..., name="urgent/high/middle/low")`
4. Показать отчёт: ✅ Создано N задач

**Важно**: Несколько вызовов одного инструмента с разными параметрами — РАЗРЕШЕНО!

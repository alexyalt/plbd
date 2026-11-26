# Журнал работ

## 2026-11-26 — этап 0
- Проанализированы `BD_table.accdb` (14 таблиц) и `BD_forms_1 (1).accdb` (17 форм, 8 отчётов, 19 VBA-модулей).
- Подтверждены числа строк полным экспортом (`mdb-count` их занижает): inspection 7 304, treat 10 291, place 312, flora 348, farma 191.
- Исправлена ошибка в `docs/ANALYSIS.md`: у `inspection` было 7 389 строк, фактически 7 304.
- Добавлены `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `docs/ANALYSIS.md`, `docs/TZ.md`, `docs/legacy/vba_source.txt`, `README.md`.
- Не проверялось: поведение форм Access в запущенном виде (Access в среде недоступен), содержимое папок `Template`, `Report_Photo`, `Report_Damage`.
- Следующий шаг: этап 1 (каркас Django, `run.py`, импорт `.accdb`).

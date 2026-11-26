# plbd

Веб-система учёта защиты зелёных насаждений (замена баз Access). Документация: `docs/TZ.md`, анализ: `docs/ANALYSIS.md`, журнал работ: `workbook.md`.

## Тестовый запуск на локальной машине

Нужны: Python 3.11+, файл `BD_table.accdb` в корне репозитория.

**Windows**
1. Установить Python с галочкой «Add Python to PATH».
2. Установить драйвер «Microsoft Access Database Engine» (ACE), разрядность как у Python (64-bit).
3. В папке репозитория выполнить `python run.py`.

**Linux / macOS**
1. Установить mdbtools (`sudo apt install mdbtools` или `brew install mdbtools`).
2. Выполнить `python3 run.py`.

При первом запуске `run.py` создаёт `.venv`, ставит зависимости, создаёт БД `data/plbd.sqlite3`, импортирует `BD_table.accdb` и открывает http://127.0.0.1:8000. Остановка: Ctrl+C.

Команды:
- `python run.py test` — тесты (16 штук).
- `python run.py manage import_access BD_table.accdb --replace` — повторный импорт с очисткой данных.
- Отчёт миграции: `data/migration_report.md`.
- Резервная копия: раздел «Сервис» в интерфейсе, файлы в `backups/`.

Что проверить вручную: «Осмотры», «Обработки» (расход считается по норме и объёму бака), «Списание ТМЦ», «Отчёты» (xlsx), «График защиты».

## Ограничения прототипа
- Не проверено на Windows с ACE (проверено на Linux с mdbtools).
- Не сделаны: справка `spravka_inObjekt`, форма СУ-21, импорт таблицы `docs`.
- Приложение слушает только 127.0.0.1, без входа в систему. Не выставлять в сеть.

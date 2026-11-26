"""Единая точка запуска.

  python run.py                       запуск сервера (при первом запуске: окружение, миграции, импорт)
  python run.py import-access <файл>  импорт из BD_table.accdb в новую БД
  python run.py test                  тесты
  python run.py manage <команда...>   любая команда Django
"""
import os
import subprocess
import sys
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
DEFAULT_ACCDB = ROOT / "BD_table.accdb"
PORT = os.environ.get("PLBD_PORT", "8000")


def venv_python():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_env():
    try:
        import django  # noqa: F401
        import openpyxl  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("PLBD_IN_VENV"):
        sys.exit("Не удалось установить зависимости из requirements.txt")
    if not venv_python().exists():
        print("Создаю окружение .venv ...")
        venv.create(VENV, with_pip=True)
    print("Устанавливаю зависимости ...")
    subprocess.check_call([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")])
    env = dict(os.environ, PLBD_IN_VENV="1")
    sys.exit(subprocess.call([str(venv_python()), str(ROOT / "run.py"), *sys.argv[1:]], env=env))


def main():
    ensure_env()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))
    import django
    from django.core.management import call_command, execute_from_command_line

    django.setup()
    args = sys.argv[1:]

    if args and args[0] == "manage":
        execute_from_command_line([sys.argv[0], *args[1:]])
        return
    if args and args[0] == "test":
        call_command("test", "core")
        return

    call_command("migrate", verbosity=0, interactive=False)

    if args and args[0] == "import-access":
        if len(args) < 2:
            sys.exit("Использование: python run.py import-access <путь к .accdb>")
        call_command("import_access", args[1])
        return

    from core.models import Inspection
    if not Inspection.objects.exists() and DEFAULT_ACCDB.exists():
        print(f"БД пуста, импортирую данные из {DEFAULT_ACCDB.name} ...")
        call_command("import_access", str(DEFAULT_ACCDB))

    url = f"http://127.0.0.1:{PORT}/"
    print(f"Система доступна по адресу {url}  (остановить: Ctrl+C)")
    if not os.environ.get("PLBD_NO_BROWSER"):
        webbrowser.open(url)
    call_command("runserver", f"127.0.0.1:{PORT}", use_reloader=False)


if __name__ == "__main__":
    main()

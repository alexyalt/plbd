import csv
import io
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TABLES = ["location", "place", "flora", "pest", "sickness", "physiology", "other", "farma",
          "person", "task", "protection", "inspection", "treat"]

_CSV_DATE_FORMATS = ["%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]


class AccessReadError(RuntimeError):
    pass


def read_table(path, table):
    """Список словарей {колонка: значение}. Значения: str, datetime, int, bool или None."""
    if sys.platform == "win32":
        try:
            import pyodbc
        except ImportError:
            pyodbc = None
        if pyodbc:
            return _read_pyodbc(pyodbc, path, table)
    if shutil.which("mdb-export"):
        return _read_mdbtools(path, table)
    raise AccessReadError(
        "Нет способа прочитать .accdb: на Windows нужен pyodbc и драйвер "
        "'Microsoft Access Database Engine' (ACE); на Linux/macOS нужен пакет mdbtools."
    )


def _read_pyodbc(pyodbc, path, table):
    drivers = [d for d in pyodbc.drivers() if "Access Driver" in d]
    if not drivers:
        raise AccessReadError("В системе не найден драйвер 'Microsoft Access Driver (*.mdb, *.accdb)' (ACE).")
    conn = pyodbc.connect(f"DRIVER={{{drivers[0]}}};DBQ={path};ReadOnly=1;")
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM [{table}]")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _read_mdbtools(path, table):
    out = subprocess.run(["mdb-export", str(path), table], capture_output=True, check=True).stdout
    return list(csv.DictReader(io.StringIO(out.decode("utf-8"), newline="")))


def col(row, name):
    """Значение колонки; допускает кириллическую 'с' вместо латинской в имени (loc_сode)."""
    if name in row:
        return row[name]
    alt = name.replace("c", "\u0441")
    if alt in row:
        return row[alt]
    for key in row:
        if key.lower() == name.lower():
            return row[key]
    return None


def text(v):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d.%m.%Y")
    return str(v).strip()


def to_int(v):
    if v is None or isinstance(v, bool):
        return int(v) if isinstance(v, bool) else None
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        return int(Decimal(s))
    except InvalidOperation:
        return None


def to_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "-1", "true", "yes", "да")


def to_decimal(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", ".").replace(" ", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in _CSV_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()

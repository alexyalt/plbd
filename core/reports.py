import io
from copy import copy
from datetime import date

import openpyxl
from django.conf import settings

TEMPLATE_DIR = settings.BASE_DIR
FIRST_ROW = 4
FOOTER_ROW = 51


def _open(name):
    wb = openpyxl.load_workbook(TEMPLATE_DIR / name)
    wb.template = False
    return wb


def _copy_style(src, dst):
    dst.font, dst.border, dst.fill = copy(src.font), copy(src.border), copy(src.fill)
    dst.number_format, dst.alignment = src.number_format, copy(src.alignment)


def writeoff_xlsx(prep, rows, total, date_from, date_to):
    wb = _open("farma_report.xltx")
    ws = wb.active
    capacity = FOOTER_ROW - FIRST_ROW - 1
    need = len(rows) + 1
    footer_row = FOOTER_ROW
    if need > capacity:
        extra = need - capacity
        ws.unmerge_cells("C51:D51")
        ws.unmerge_cells("E51:F51")
        ws.insert_rows(FOOTER_ROW, extra)
        footer_row = FOOTER_ROW + extra
        ws.merge_cells(f"C{footer_row}:D{footer_row}")
        ws.merge_cells(f"E{footer_row}:F{footer_row}")
    period = " ".join(filter(None, [
        f"с {date_from:%d.%m.%Y}" if date_from else "", f"по {date_to:%d.%m.%Y}" if date_to else ""]))
    ws["A2"] = f"{prep.name}. {period}".strip(". ")
    unit = prep.stock_unit or prep.unit
    for i, r in enumerate(rows):
        n = FIRST_ROW + i
        t = r.treatment
        desc = t.inspection.description if t.inspection_id else ""
        values = [t.date, t.treat_type, prep.name, float(r.quantity or 0), unit, desc]
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=n, column=c, value=v)
            _copy_style(ws.cell(row=FIRST_ROW, column=c), cell)
        ws.cell(row=n, column=1).number_format = "DD.MM.YYYY"
    tr = FIRST_ROW + len(rows)
    ws.cell(row=tr, column=3, value="Итого")
    ws.cell(row=tr, column=4, value=float(total or 0))
    ws.cell(row=tr, column=5, value=unit)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

import io
import warnings
from copy import copy

import openpyxl
from django.conf import settings
from openpyxl.worksheet.cell_range import CellRange

TEMPLATE_DIR = settings.BASE_DIR
DATE_FMT = "DD.MM.YYYY"


def _open(name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(TEMPLATE_DIR / name)
    wb.template = False
    return wb


def _bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _copy_style(src, dst):
    dst.font, dst.border, dst.fill = copy(src.font), copy(src.border), copy(src.fill)
    dst.number_format, dst.alignment = src.number_format, copy(src.alignment)


def _write_rows(ws, first_row, rows, style_row=None):
    style_row = style_row or first_row
    for i, values in enumerate(rows):
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=first_row + i, column=c, value=v)
            _copy_style(ws.cell(row=style_row, column=c), cell)
            if hasattr(v, "year"):
                cell.number_format = DATE_FMT


def _shift_footer(ws, first_row, footer_row, needed, merges):
    capacity = footer_row - first_row - 1
    if needed <= capacity:
        return footer_row
    extra = needed - capacity
    for m in merges:
        ws.unmerge_cells(m)
    ws.insert_rows(footer_row, extra)
    for m in merges:
        cr = CellRange(m)
        cr.shift(row_shift=extra)
        ws.merge_cells(cr.coord)
    return footer_row + extra


def _reagent_values(r, with_description=True):
    t = r.treatment
    prep = r.preparation
    desc = t.inspection.description if (with_description and t.inspection_id) else ""
    return [t.date, t.treat_type, prep.name, float(r.quantity or 0), prep.stock_unit or prep.unit, desc]


def writeoff_xlsx(prep, rows, total, date_from, date_to):
    wb = _open("farma_report.xltx")
    ws = wb.active
    _shift_footer(ws, 4, 51, len(rows) + 1, ["C51:D51", "E51:F51"])
    period = " ".join(filter(None, [
        f"с {date_from:%d.%m.%Y}" if date_from else "", f"по {date_to:%d.%m.%Y}" if date_to else ""]))
    ws["A2"] = f"{prep.name}. {period}".strip(". ")
    _write_rows(ws, 4, [_reagent_values(r) for r in rows])
    tr = 4 + len(rows)
    ws.cell(row=tr, column=3, value="Итого")
    ws.cell(row=tr, column=4, value=float(total or 0))
    ws.cell(row=tr, column=5, value=prep.stock_unit or prep.unit)
    return _bytes(wb)


def treatment_report_xlsx(location, plant, rows):
    wb = _open("treet_report (1).xltx")
    ws = wb.active
    _shift_footer(ws, 4, 40, len(rows), ["B40:D40", "B42:C42", "D42:F42"])
    ws["A2"] = f"Объект: {location or 'все'}"
    ws["D2"] = str(plant) if plant else "все"
    _write_rows(ws, 4, [_reagent_values(r) for r in rows])
    return _bytes(wb)


def journal_xlsx(rows):
    wb = _open("work_book (1).xltx")
    ws = wb.active
    values = []
    for r in rows:
        t = r.treatment
        values.append([t.date, t.location.name if t.location else "", t.plant.name if t.plant else "",
                       t.inspection.legacy_id if t.inspection_id else "", t.treat_type, r.preparation.name,
                       float(r.quantity or 0), r.preparation.stock_unit or r.preparation.unit,
                       str(t.person) if t.person else "", t.result])
    _write_rows(ws, 3, values, style_row=3)
    return _bytes(wb)


def inspection_act_xlsx(inspections):
    wb = _open("insp_report (1).xltx")
    ws = wb.active
    signature = []
    for r in (131, 132, 133):
        signature.append((ws.cell(row=r, column=4).value, ws.cell(row=r, column=7).value))
        ws.cell(row=r, column=4).value = None
        ws.cell(row=r, column=7).value = None
    values = []
    for i in inspections:
        values.append([i.legacy_id, i.location.name if i.location else "", i.place.name if i.place else "",
                       i.plant.name if i.plant else "", i.inv, i.count, i.description, i.reason_kind,
                       i.reason_short, i.prescription, i.task])
    _write_rows(ws, 2, values, style_row=2)
    start = 2 + len(values) + 1
    for k, (role, name) in enumerate(signature):
        ws.cell(row=start + k, column=4, value=role)
        ws.cell(row=start + k, column=7, value=name)
    return _bytes(wb)

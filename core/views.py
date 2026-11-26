import json
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Sum
from django.forms import modelform_factory
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import reports
from .forms import InspectionForm, ReagentFormSet, TreatmentForm, WriteoffFilter
from .models import (AuditLog, Cause, Inspection, Location, Person, Place, Plant, Preparation,
                     ProtectionRule, TaskType, Treatment, TreatmentReagent)
from .accessdb import norm

CATALOGS = {
    "location": (Location, ["name", "code"], ["name", "code"]),
    "place": (Place, ["location", "name", "plan", "content"], ["name", "parent_raw", "content", "location__name"]),
    "plant": (Plant, ["name", "latin"], ["name", "latin"]),
    "cause": (Cause, ["kind", "name", "description"], ["name", "description"]),
    "preparation": (Preparation, ["name", "dose_per_10l", "unit", "kind", "usage", "stock_code"],
                    ["name", "kind", "stock_name", "stock_code", "active_substance"]),
    "person": (Person, ["surname", "name", "patronymic", "post"], ["surname", "name", "post"]),
    "tasktype": (TaskType, ["name"], ["name"]),
    "protectionrule": (ProtectionRule, ["week", "phenology", "plant", "targets", "preparations"],
                       ["phenology", "targets", "preparations", "plant__name"]),
}


def audit(action, obj):
    AuditLog.objects.create(action=action, model=obj._meta.verbose_name, object_id=str(obj.pk or ""),
                            text=str(obj)[:500])


def paginate(request, qs, per=50):
    page = Paginator(qs, per).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def cell(obj, name):
    f = obj._meta.get_field(name)
    v = getattr(obj, f"get_{name}_display")() if f.choices else getattr(obj, name)
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return "да" if v else ""
    if isinstance(v, Decimal):
        return f"{v.normalize():f}"
    return v


def dashboard(request):
    ctx = {
        "counts": [
            ("Осмотры", Inspection.objects.count()),
            ("В работе", Inspection.objects.filter(in_work=True, done=False).count()),
            ("Обработки", Treatment.objects.count()),
            ("Не списано (строк)", TreatmentReagent.objects.filter(written_off=False).count()),
            ("Растения", Plant.objects.count()),
            ("Препараты", Preparation.objects.filter(merged_into__isnull=True).count()),
        ],
        "recent_inspections": Inspection.objects.select_related("location", "plant")[:8],
        "recent_treatments": Treatment.objects.select_related("location", "plant", "person")[:8],
    }
    return render(request, "core/dashboard.html", ctx)


def catalogs(request):
    items = []
    for slug, (model, _, _) in CATALOGS.items():
        qs = model.objects.all()
        if model is Preparation:
            qs = qs.filter(merged_into__isnull=True)
        items.append((slug, model._meta.verbose_name_plural.capitalize(), qs.count()))
    return render(request, "core/catalogs.html", {"items": items})


def _catalog(slug):
    if slug not in CATALOGS:
        raise Http404
    return CATALOGS[slug]


def catalog_list(request, slug):
    model, columns, search = _catalog(slug)
    qs = model.objects.all()
    if model is Preparation:
        qs = qs.filter(merged_into__isnull=True)
    q = request.GET.get("q", "").strip()
    if q:
        cond = Q()
        for f in search:
            cond |= Q(**{f"{f}__icontains": q})
        qs = qs.filter(cond)
    has_ph = any(f.name == "is_placeholder" for f in model._meta.fields)
    if has_ph and request.GET.get("placeholder"):
        qs = qs.filter(is_placeholder=True)
    sort = request.GET.get("sort", "")
    if sort.lstrip("-") in columns:
        qs = qs.order_by(sort)
    page, qstr = paginate(request, qs)
    headers = [model._meta.get_field(c).verbose_name for c in columns]
    rows = [(o.pk, [cell(o, c) for c in columns]) for o in page]
    return render(request, "core/catalog_list.html", {
        "slug": slug, "title": model._meta.verbose_name_plural.capitalize(), "headers": headers,
        "columns": columns, "rows": rows, "page": page, "qstr": qstr, "q": q, "has_placeholder": has_ph,
        "only_placeholder": bool(request.GET.get("placeholder"))})


def catalog_edit(request, slug, pk=None):
    model, _, _ = _catalog(slug)
    obj = get_object_or_404(model, pk=pk) if pk else None
    Form = modelform_factory(model, fields="__all__")
    form = Form(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        audit("изменение" if pk else "создание", saved)
        messages.success(request, "Сохранено")
        return redirect("catalog_list", slug=slug)
    return render(request, "core/form.html", {
        "form": form, "title": ("Правка: " if pk else "Новая запись: ") + model._meta.verbose_name,
        "back": f"/catalog/{slug}/"})


@require_POST
def catalog_delete(request, slug, pk):
    model, _, _ = _catalog(slug)
    obj = get_object_or_404(model, pk=pk)
    try:
        label = str(obj)
        obj.delete()
        AuditLog.objects.create(action="удаление", model=model._meta.verbose_name, object_id=str(pk), text=label[:500])
        messages.success(request, "Удалено")
    except ProtectedError:
        messages.error(request, "Нельзя удалить: на запись есть ссылки (осмотры или обработки).")
    return redirect("catalog_list", slug=slug)


def inspection_list(request):
    g = request.GET
    qs = Inspection.objects.select_related("location", "plant", "place")
    if g.get("q"):
        q = g["q"].strip()
        qs = qs.filter(Q(description__icontains=q) | Q(reason_short__icontains=q) | Q(task__icontains=q)
                       | Q(plant__name__icontains=q) | Q(inv__icontains=q))
    if g.get("date_from"):
        qs = qs.filter(date__gte=g["date_from"])
    if g.get("date_to"):
        qs = qs.filter(date__lte=g["date_to"])
    if g.get("location"):
        qs = qs.filter(location_id=g["location"])
    if g.get("plant"):
        qs = qs.filter(plant_id=g["plant"])
    status = g.get("status")
    if status == "work":
        qs = qs.filter(in_work=True, done=False)
    elif status == "done":
        qs = qs.filter(done=True)
    elif status == "open":
        qs = qs.filter(done=False)
    page, qstr = paginate(request, qs)
    return render(request, "core/inspection_list.html", {
        "page": page, "qstr": qstr, "g": g, "locations": Location.objects.all(), "plants": Plant.objects.all()})


def inspection_detail(request, pk):
    obj = get_object_or_404(Inspection.objects.select_related("location", "plant", "place", "author", "prev"), pk=pk)
    treatments = obj.treatments.select_related("person").prefetch_related("reagents__preparation")
    return render(request, "core/inspection_detail.html", {"o": obj, "treatments": treatments})


def inspection_edit(request, pk=None):
    obj = get_object_or_404(Inspection, pk=pk) if pk else None
    initial = {} if obj else {"date": date.today()}
    form = InspectionForm(request.POST or None, instance=obj, initial=initial)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if saved.legacy_id is None:
            saved.legacy_id = _next_inspection_number(saved.date or date.today())
        saved.save()
        audit("изменение" if pk else "создание", saved)
        messages.success(request, "Осмотр сохранён")
        return redirect("inspection_detail", pk=saved.pk)
    return render(request, "core/form.html", {
        "form": form, "title": f"Правка: {obj}" if obj else "Новый акт осмотра", "back": "/inspections/"})


def _next_inspection_number(d):
    base = int(d.strftime("%Y%m%d")) * 100
    last = Inspection.objects.filter(legacy_id__gt=base, legacy_id__lt=base + 100).order_by("-legacy_id").first()
    return (last.legacy_id + 1) if last else base + 1


@require_POST
def inspection_done(request, pk):
    obj = get_object_or_404(Inspection, pk=pk)
    obj.done = not obj.done
    if obj.done:
        obj.in_work = False
    obj.save(update_fields=["done", "in_work"])
    audit("выполнено" if obj.done else "снята отметка выполнения", obj)
    return redirect("inspection_detail", pk=pk)


@require_POST
def inspection_delete(request, pk):
    obj = get_object_or_404(Inspection, pk=pk)
    if obj.treatments.exists():
        messages.error(request, "Нельзя удалить осмотр: к нему привязаны обработки.")
        return redirect("inspection_detail", pk=pk)
    label = str(obj)
    obj.delete()
    AuditLog.objects.create(action="удаление", model="акт осмотра", object_id=str(pk), text=label)
    messages.success(request, "Осмотр удалён")
    return redirect("inspection_list")


def treatment_list(request):
    g = request.GET
    qs = Treatment.objects.select_related("location", "plant", "person").prefetch_related("reagents__preparation")
    if g.get("q"):
        q = g["q"].strip()
        qs = qs.filter(Q(plant__name__icontains=q) | Q(result__icontains=q) | Q(task_text__icontains=q))
    if g.get("date_from"):
        qs = qs.filter(date__gte=g["date_from"])
    if g.get("date_to"):
        qs = qs.filter(date__lte=g["date_to"])
    for key, field in (("location", "location_id"), ("plant", "plant_id"), ("person", "person_id"),
                       ("preparation", "reagents__preparation_id")):
        if g.get(key):
            qs = qs.filter(**{field: g[key]})
    if g.get("wo") == "no":
        qs = qs.filter(reagents__written_off=False)
    elif g.get("wo") == "yes":
        qs = qs.filter(reagents__written_off=True)
    qs = qs.distinct()
    page, qstr = paginate(request, qs)
    return render(request, "core/treatment_list.html", {
        "page": page, "qstr": qstr, "g": g, "locations": Location.objects.all(), "plants": Plant.objects.all(),
        "persons": Person.objects.all(), "preparations": Preparation.objects.filter(merged_into__isnull=True)})


def treatment_edit(request, pk=None):
    obj = get_object_or_404(Treatment, pk=pk) if pk else None
    initial = {}
    if not obj:
        initial = {"date": date.today(), "treat_type": "Обработка", "gasoline": True}
        ins = Inspection.objects.filter(pk=request.GET.get("inspection")).first()
        if ins:
            initial.update(inspection=ins.pk, location=ins.location_id, plant=ins.plant_id,
                           task_text=ins.task)
    form = TreatmentForm(request.POST or None, instance=obj, initial=initial)
    formset = ReagentFormSet(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            saved = form.save(commit=False)
            if saved.inspection_id:
                saved.inspection_legacy_id = saved.inspection.legacy_id
            saved.save()
            formset.instance = saved
            formset.save()
        audit("изменение" if pk else "создание", saved)
        messages.success(request, "Обработка сохранена")
        return redirect("treatment_list")
    doses = {p.pk: str(p.dose_per_10l) for p in Preparation.objects.filter(dose_per_10l__isnull=False)}
    return render(request, "core/treatment_form.html", {
        "form": form, "formset": formset, "doses": json.dumps(doses),
        "title": f"Правка: {obj}" if obj else "Новая обработка"})


@require_POST
def treatment_delete(request, pk):
    obj = get_object_or_404(Treatment, pk=pk)
    if obj.reagents.filter(written_off=True).exists():
        messages.error(request, "Нельзя удалить обработку: часть препаратов уже списана.")
        return redirect("treatment_list")
    label = str(obj)
    obj.delete()
    AuditLog.objects.create(action="удаление", model="обработка", object_id=str(pk), text=label)
    messages.success(request, "Обработка удалена")
    return redirect("treatment_list")


def _writeoff_rows(prep, date_from, date_to, location=None):
    qs = (TreatmentReagent.objects.filter(preparation=prep, written_off=False)
          .select_related("treatment__location").order_by("treatment__date", "treatment_id"))
    if date_from:
        qs = qs.filter(treatment__date__gte=date_from)
    if date_to:
        qs = qs.filter(treatment__date__lte=date_to)
    return qs


def writeoff(request):
    form = WriteoffFilter(request.GET or None)
    rows, total, prep = [], None, None
    if form.is_valid() and form.cleaned_data["preparation"]:
        prep = form.cleaned_data["preparation"]
        rows = list(_writeoff_rows(prep, form.cleaned_data["date_from"], form.cleaned_data["date_to"]))
        total = sum((r.quantity or 0) for r in rows)
        if request.GET.get("export") == "xlsx":
            data = reports.writeoff_xlsx(prep, rows, total, form.cleaned_data["date_from"], form.cleaned_data["date_to"])
            resp = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = f'attachment; filename="writeoff_{prep.pk}.xlsx"'
            return resp
    return render(request, "core/writeoff.html", {
        "form": form, "rows": rows, "total": total, "prep": prep, "qstr": request.GET.urlencode()})


@require_POST
def writeoff_confirm(request):
    ids = request.POST.getlist("ids")
    n = TreatmentReagent.objects.filter(pk__in=ids, written_off=False).update(written_off=True)
    AuditLog.objects.create(action="списание", model="препарат обработки", object_id="",
                            text=f"Списано строк: {n} ({request.POST.get('label', '')})"[:500])
    messages.success(request, f"Списано строк: {n}")
    return redirect(f"/writeoff/?{request.POST.get('qstr', '')}")


def access_week(d):
    offset = (date(d.year, 1, 1).weekday() + 1) % 7
    return (d.timetuple().tm_yday - 1 + offset) // 7 + 1


def protection(request):
    try:
        base = datetime.strptime(request.GET.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        base = date.today()
    week = access_week(base)
    rules = []
    for r in ProtectionRule.objects.filter(week=week).select_related("plant"):
        places = []
        if r.plant:
            places = Place.objects.filter(content__icontains=r.plant.name).select_related("location")[:30]
        rules.append((r, places))
    return render(request, "core/protection.html", {
        "base": base, "week": week, "rules": rules,
        "prev": base - timedelta(days=7), "next": base + timedelta(days=7),
        "all_rules": ProtectionRule.objects.select_related("plant")})


def duplicates(request):
    if request.method == "POST":
        primary = get_object_or_404(Preparation, pk=request.POST.get("primary"))
        others = list(Preparation.objects.filter(pk__in=request.POST.getlist("members"),
                                                 merged_into__isnull=True).exclude(pk=primary.pk))
        with transaction.atomic():
            for o in others:
                for f in ("dose_per_10l", "unit", "kind", "usage", "active_substance", "stock_name",
                          "stock_unit", "stock_code"):
                    if not getattr(primary, f) and getattr(o, f):
                        setattr(primary, f, getattr(o, f))
            primary.save()
            TreatmentReagent.objects.filter(preparation__in=others).update(preparation=primary)
            Preparation.objects.filter(pk__in=[o.pk for o in others]).update(merged_into=primary)
        AuditLog.objects.create(action="слияние", model="препарат", object_id=str(primary.pk),
                                text=f"{primary.name}: объединено записей {len(others)}")
        messages.success(request, f"Объединено в «{primary.name}»: {len(others)}")
        return redirect("duplicates")
    groups = {}
    for p in Preparation.objects.filter(merged_into__isnull=True).annotate(n=Count("usages")):
        groups.setdefault(norm(p.name), []).append(p)
    groups = [g for g in groups.values() if len(g) > 1]
    for g in groups:
        g.sort(key=lambda p: -p.n)
    return render(request, "core/duplicates.html", {"groups": groups})


def tools(request):
    backups = []
    bdir = settings.BASE_DIR / "backups"
    if bdir.exists():
        backups = sorted(bdir.glob("*.sqlite3"), reverse=True)[:20]
    report = settings.DATA_DIR / "migration_report.md"
    return render(request, "core/tools.html", {
        "backups": [(b.name, round(b.stat().st_size / 1e6, 1)) for b in backups],
        "has_report": report.exists(),
        "placeholders": [(m._meta.verbose_name_plural, m.objects.filter(is_placeholder=True).count(), slug)
                         for slug, (m, _, _) in CATALOGS.items()
                         if any(f.name == "is_placeholder" for f in m._meta.fields)]})


@require_POST
def backup(request):
    bdir = settings.BASE_DIR / "backups"
    bdir.mkdir(exist_ok=True)
    dest = bdir / f"plbd_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
    src = sqlite3.connect(settings.DATABASES["default"]["NAME"])
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    messages.success(request, f"Резервная копия: backups/{dest.name}")
    return redirect("tools")


def migration_report(request):
    path = settings.DATA_DIR / "migration_report.md"
    if not path.exists():
        raise Http404
    return HttpResponse(path.read_text(encoding="utf-8"), content_type="text/plain; charset=utf-8")


def audit_log(request):
    page, qstr = paginate(request, AuditLog.objects.all())
    return render(request, "core/audit.html", {"page": page, "qstr": qstr})

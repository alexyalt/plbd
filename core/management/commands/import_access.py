from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core import accessdb as A
from core.models import (Cause, Inspection, Location, Person, Place, Plant, Preparation,
                         ProtectionRule, TaskType, Treatment, TreatmentReagent)

CAUSE_TABLES = [
    ("pest", Cause.PEST, "pest", "pest_lat"),
    ("sickness", Cause.DISEASE, "sickness", "sickness_lat"),
    ("physiology", Cause.PHYSIOLOGY, "physiology", "physiology_des"),
    ("other", Cause.OTHER, "other", "other_des"),
]


class Importer:
    def __init__(self, path):
        self.path = path
        self.src = {}
        self.report = defaultdict(list)
        self.counts = {}

    def note(self, section, msg):
        self.report[section].append(msg)

    def load(self):
        for t in A.TABLES:
            self.src[t] = A.read_table(self.path, t)

    def run(self):
        self.load()
        self.dictionaries()
        self.inspections()
        self.treatments()
        self.protection()

    def dictionaries(self):
        S = self.src
        self.loc_idx = {}
        for r in S["location"]:
            name = A.text(A.col(r, "location"))
            if not name:
                continue
            k = A.norm(name)
            if k in self.loc_idx:
                self.note("Дубли объектов (пропущены)", name)
                continue
            self.loc_idx[k] = Location.objects.create(
                name=name, code=A.text(A.col(r, "loc_code")), legacy_id=A.to_int(A.col(r, "ID")))

        self.plant_idx = {}
        for r in S["flora"]:
            name = A.text(A.col(r, "flora_name"))
            if not name:
                continue
            k = A.norm(name)
            if k in self.plant_idx:
                self.note("Дубли растений (пропущены)", name)
                continue
            self.plant_idx[k] = Plant.objects.create(
                name=name, latin=A.text(A.col(r, "flora_lat")), legacy_id=A.to_int(A.col(r, "ID")))

        self.place_by_id = {}
        for r in S["place"]:
            parent = A.text(A.col(r, "parent"))
            loc = self.loc_idx.get(A.norm(parent))
            if parent and not loc:
                self.note("Куртины с неизвестным объектом (объект не задан)", f"{parent} / {A.text(A.col(r, 'place'))}")
            pid = A.to_int(A.col(r, "id"))
            self.place_by_id[pid] = Place.objects.create(
                location=loc, name=A.text(A.col(r, "place")), plan=A.text(A.col(r, "plan")),
                content=A.text(A.col(r, "content")), parent_raw=parent, legacy_id=pid)

        for table, kind, name_col, desc_col in CAUSE_TABLES:
            Cause.objects.bulk_create([
                Cause(kind=kind, name=A.text(A.col(r, name_col)), description=A.text(A.col(r, desc_col)),
                      legacy_id=A.to_int(A.col(r, "ID")))
                for r in S[table]])

        self.prep_idx = {}
        for r in S["farma"]:
            raw_name = A.text(A.col(r, "farma_name"))
            lid = A.to_int(A.col(r, "ID"))
            dose = A.to_decimal(A.col(r, "n_p"))
            p = Preparation.objects.create(
                name=raw_name or f"(без названия, id {lid})",
                dose_per_10l=dose, dose_raw=A.text(A.col(r, "n_p")), unit=A.text(A.col(r, "pref")),
                kind=A.text(A.col(r, "clase")), usage=A.text(A.col(r, "use")),
                stock_name=A.text(A.col(r, "sklad_name")), stock_unit=A.text(A.col(r, "sklad_pref")),
                stock_code=A.text(A.col(r, "farma_code")), legacy_id=lid)
            if not raw_name:
                self.note("Препараты без названия", f"id {lid}")
                continue
            k = A.norm(raw_name)
            if k in self.prep_idx:
                self.note("Дубли препаратов (ссылки идут на первый с нормой)", f"{raw_name} (id {lid})")
                if self.prep_idx[k].dose_per_10l is None and dose is not None:
                    self.prep_idx[k] = p
            else:
                self.prep_idx[k] = p

        self.person_by_id = {}
        self.person_idx = {}
        for r in S["person"]:
            p = Person.objects.create(
                surname=A.text(A.col(r, "surname")), name=A.text(A.col(r, "name")),
                patronymic=A.text(A.col(r, "parent")), post=A.text(A.col(r, "post")),
                legacy_id=A.to_int(A.col(r, "ID")))
            self.person_by_id[p.legacy_id] = p
            self.person_idx.setdefault(A.norm(str(p)), p)
            self.person_idx.setdefault(A.norm(p.surname), p)

        TaskType.objects.bulk_create([
            TaskType(name=A.text(A.col(r, "task_name")), legacy_id=A.to_int(A.col(r, "id"))) for r in S["task"]])

    def resolve(self, raw, idx, model, field, section, **extra):
        raw = A.text(raw)
        if not raw:
            return None
        k = A.norm(raw)
        obj = idx.get(k)
        if obj is None:
            obj = model.objects.create(**{field: raw}, is_placeholder=True, **extra)
            idx[k] = obj
            self.note(section, raw)
        return obj

    def resolve_person(self, raw):
        raw = A.text(raw)
        if not raw:
            return None
        k = A.norm(raw)
        obj = self.person_idx.get(k)
        if obj is None:
            surname = k.split(" ")[0]
            obj = self.person_idx.get(surname)
        if obj is None:
            obj = Person.objects.create(surname=raw, is_placeholder=True)
            self.person_idx[k] = obj
            self.note("Сотрудники, которых нет в справочнике (созданы как заглушки)", raw)
        return obj

    def inspections(self):
        rows = self.src["inspection"]
        objs, prev_ids = [], {}
        bad_date = 0
        lost_place = 0
        for r in rows:
            lid = A.to_int(A.col(r, "id"))
            d = A.to_date(A.col(r, "data"))
            if d is None:
                bad_date += 1
                self.note("Осмотры без даты", f"№ {lid}")
            pid = A.to_int(A.col(r, "place"))
            place = self.place_by_id.get(pid)
            if pid is not None and place is None:
                lost_place += 1
            objs.append(Inspection(
                legacy_id=lid, date=d,
                location=self.resolve(A.col(r, "location"), self.loc_idx, Location, "name",
                                      "Объекты, которых нет в справочнике (созданы как заглушки)"),
                place=place,
                plant=self.resolve(A.col(r, "flora"), self.plant_idx, Plant, "name",
                                   "Растения, которых нет в справочнике (созданы как заглушки)"),
                inv=A.text(A.col(r, "inv")), count=A.text(A.col(r, "count")),
                description=A.text(A.col(r, "description")),
                reason_kind=A.text(A.col(r, "reason_tip")), reason_short=A.text(A.col(r, "reason_short")),
                reason_text=A.text(A.col(r, "reason")), prescription=A.text(A.col(r, "farma")),
                task=A.text(A.col(r, "task")), task_date=A.to_date(A.col(r, "task_data")),
                done=A.to_bool(A.col(r, "done")), in_work=A.to_bool(A.col(r, "inWork")),
                author=self.person_by_id.get(A.to_int(A.col(r, "Autor"))),
                reagents_raw="; ".join(filter(None, (A.text(A.col(r, f"reag{i}")) for i in range(1, 5))))))
            prev_ids[lid] = A.to_int(A.col(r, "prev_insp"))
        if lost_place:
            self.note("Осмотры со ссылкой на несуществующую куртину (куртина не задана)", f"{lost_place} шт.")
        Inspection.objects.bulk_create(objs, batch_size=500)
        by_legacy = {i.legacy_id: i for i in Inspection.objects.all()}
        self.insp_by_legacy = by_legacy
        upd = []
        for lid, prev in prev_ids.items():
            if prev and prev in by_legacy and lid in by_legacy:
                by_legacy[lid].prev = by_legacy[prev]
                upd.append(by_legacy[lid])
            elif prev:
                self.note("Ссылка на предыдущий осмотр не найдена", f"осмотр {lid} -> {prev}")
        Inspection.objects.bulk_update(upd, ["prev"], batch_size=500)

    def treatments(self):
        rows = self.src["treat"]
        treat_objs, reag_src = [], {}
        orphan = 0
        for r in rows:
            lid = A.to_int(A.col(r, "count"))
            ins_id = A.to_int(A.col(r, "reason"))
            ins = self.insp_by_legacy.get(ins_id)
            if ins_id and not ins:
                orphan += 1
            t = Treatment(
                legacy_id=lid, date=A.to_date(A.col(r, "data")),
                location=self.resolve(A.col(r, "location"), self.loc_idx, Location, "name",
                                      "Объекты, которых нет в справочнике (созданы как заглушки)"),
                plant=self.resolve(A.col(r, "flora"), self.plant_idx, Plant, "name",
                                   "Растения, которых нет в справочнике (созданы как заглушки)"),
                person=self.resolve_person(A.col(r, "person")),
                inspection=ins, inspection_legacy_id=ins_id, tank=A.to_int(A.col(r, "tank")),
                treat_type=A.text(A.col(r, "Treat_type")), gasoline=A.to_bool(A.col(r, "gasolin")),
                result=A.text(A.col(r, "result")), task_text=A.text(A.col(r, "task_insp")))
            treat_objs.append(t)
            lines = []
            for i in range(1, 5):
                name = A.text(A.col(r, f"reag{i}"))
                if name:
                    lines.append((name, A.to_decimal(A.col(r, f"reag_count{i}"))))
            reag_src[lid] = (lines, A.to_bool(A.col(r, "write-down")))
            if A.text(A.col(r, "data")) and t.date is None:
                self.note("Обработки с нечитаемой датой", f"№ {lid}")
        if orphan:
            self.note("Обработки со ссылкой на несуществующий осмотр", f"{orphan} шт.")
        Treatment.objects.bulk_create(treat_objs, batch_size=500)
        by_legacy = dict(Treatment.objects.values_list("legacy_id", "id"))
        reagents = []
        for lid, (lines, wd) in reag_src.items():
            for name, qty in lines:
                prep = self.resolve(name, self.prep_idx, Preparation, "name",
                                    "Препараты, которых нет в справочнике (созданы как заглушки)")
                reagents.append(TreatmentReagent(treatment_id=by_legacy[lid], preparation=prep, quantity=qty, written_off=wd))
        TreatmentReagent.objects.bulk_create(reagents, batch_size=1000)

    def protection(self):
        for r in self.src["protection"]:
            sid = A.to_int(A.col(r, "prot_subject"))
            plant = Plant.objects.filter(legacy_id=sid).first() if sid else None
            ProtectionRule.objects.create(
                week=A.to_int(A.col(r, "prot_data")) or 0, phenology=A.text(A.col(r, "prot_phenology")),
                subject_id=sid, plant=plant, targets=A.text(A.col(r, "prot_object")),
                preparations=A.text(A.col(r, "prot_farma")), legacy_id=A.to_int(A.col(r, "id")))

    def write_report(self, out_path):
        pairs = [("location", Location), ("place", Place), ("flora", Plant), ("farma", Preparation),
                 ("person", Person), ("task", TaskType), ("protection", ProtectionRule),
                 ("inspection", Inspection), ("treat", Treatment)]
        lines = [f"# Отчёт миграции\n", f"Источник: `{Path(self.path).name}`, время: {datetime.now():%Y-%m-%d %H:%M}\n",
                 "## Количество строк\n", "| Таблица Access | В источнике | В новой БД | Заглушки (созданы при импорте) |",
                 "|---|---|---|---|"]
        for t, m in pairs:
            ph = m.objects.filter(is_placeholder=True).count() if hasattr(m, "is_placeholder") else 0
            lines.append(f"| {t} | {len(self.src[t])} | {m.objects.count()} | {ph} |")
        causes = sum(len(self.src[t]) for t, *_ in CAUSE_TABLES)
        lines.append(f"| pest+sickness+physiology+other | {causes} | {Cause.objects.count()} | 0 |")
        lines.append(f"| строки препаратов в treat (reag1..4) | - | {TreatmentReagent.objects.count()} | - |")
        for section, items in self.report.items():
            lines.append(f"\n## {section}: {len(items)}\n")
            counts = Counter(items)
            for item, n in list(counts.items())[:60]:
                lines.append(f"- {item}" + (f" (x{n})" if n > 1 else ""))
            if len(counts) > 60:
                lines.append(f"- ... и ещё {len(counts) - 60}")
        Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "\n".join(lines[:16])


class Command(BaseCommand):
    help = "Импорт данных из BD_table.accdb"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--replace", action="store_true", help="удалить существующие данные перед импортом")

    def handle(self, *args, path, replace, **opts):
        path = Path(path)
        if not path.exists():
            raise CommandError(f"Файл не найден: {path}")
        if Inspection.objects.exists() or Treatment.objects.exists():
            if not replace:
                raise CommandError("В БД уже есть данные. Для повторного импорта добавьте --replace.")
        try:
            with transaction.atomic():
                if replace:
                    for m in (TreatmentReagent, Treatment, Inspection, ProtectionRule, TaskType, Person,
                              Preparation, Cause, Place, Plant, Location):
                        m.objects.all().delete()
                imp = Importer(path)
                imp.run()
        except A.AccessReadError as e:
            raise CommandError(str(e))
        summary = imp.write_report(settings.DATA_DIR / "migration_report.md")
        self.stdout.write(summary)
        self.stdout.write(f"Полный отчёт: {settings.DATA_DIR / 'migration_report.md'}")

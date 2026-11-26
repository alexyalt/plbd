from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import accessdb
from core.management.commands.import_access import Importer
from core.models import (Inspection, Location, Person, Plant, Preparation, Treatment, TreatmentReagent)
from core.views import access_week


def make_base():
    loc = Location.objects.create(name="КП-3", code="12")
    plant = Plant.objects.create(name="Роза")
    person = Person.objects.create(surname="Иванов", name="Иван", patronymic="Иванович")
    prep = Preparation.objects.create(name="Хорус", dose_per_10l=Decimal("25"), unit="г", stock_unit="г")
    return loc, plant, person, prep


class FormulaTests(TestCase):
    def test_quantity_for_tank(self):
        _, _, _, prep = make_base()
        self.assertEqual(prep.quantity_for_tank(15), Decimal("37.50"))
        self.assertEqual(prep.quantity_for_tank(10), Decimal("25.00"))

    def test_no_dose_gives_none(self):
        p = Preparation.objects.create(name="Без нормы")
        self.assertIsNone(p.quantity_for_tank(10))

    def test_access_week_matches_datepart_ww(self):
        self.assertEqual(access_week(date(2026, 1, 1)), 1)
        self.assertEqual(access_week(date(2026, 1, 3)), 1)
        self.assertEqual(access_week(date(2026, 1, 4)), 2)
        self.assertEqual(access_week(date(2026, 11, 26)), 48)


class ViewFlowTests(TestCase):
    def setUp(self):
        self.loc, self.plant, self.person, self.prep = make_base()

    def post_treatment(self, qty=""):
        data = {
            "date": "2026-05-10", "location": self.loc.pk, "plant": self.plant.pk, "person": self.person.pk,
            "tank": 15, "treat_type": "Обработка", "gasoline": "on", "result": "", "task_text": "",
            "reagents-TOTAL_FORMS": 1, "reagents-INITIAL_FORMS": 0, "reagents-MIN_NUM_FORMS": 0,
            "reagents-MAX_NUM_FORMS": 4,
            "reagents-0-preparation": self.prep.pk, "reagents-0-quantity": qty,
        }
        return self.client.post(reverse("treatment_new"), data)

    def test_treatment_quantity_autocalculated(self):
        r = self.post_treatment()
        self.assertEqual(r.status_code, 302)
        line = TreatmentReagent.objects.get()
        self.assertEqual(line.quantity, Decimal("37.50"))

    def test_treatment_explicit_quantity_kept(self):
        self.post_treatment(qty="40")
        self.assertEqual(TreatmentReagent.objects.get().quantity, Decimal("40.00"))

    def test_inspection_create_assigns_number(self):
        r = self.client.post(reverse("inspection_new"), {
            "date": "2026-05-10", "location": self.loc.pk, "plant": self.plant.pk, "description": "тля"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Inspection.objects.get().legacy_id, 2026051001)

    def test_writeoff_confirm_marks_only_selected(self):
        t = Treatment.objects.create(date=date(2026, 5, 1), location=self.loc, tank=10)
        a = TreatmentReagent.objects.create(treatment=t, preparation=self.prep)
        b = TreatmentReagent.objects.create(treatment=t, preparation=self.prep)
        page = self.client.get(reverse("writeoff"), {"preparation": self.prep.pk})
        self.assertEqual(len(page.context["rows"]), 2)
        self.client.post(reverse("writeoff_confirm"), {"ids": [a.pk], "qstr": f"preparation={self.prep.pk}"})
        a.refresh_from_db(), b.refresh_from_db()
        self.assertTrue(a.written_off)
        self.assertFalse(b.written_off)
        page = self.client.get(reverse("writeoff"), {"preparation": self.prep.pk})
        self.assertEqual(len(page.context["rows"]), 1)

    def test_writeoff_xlsx_export(self):
        t = Treatment.objects.create(date=date(2026, 5, 1), location=self.loc, tank=10, treat_type="Обработка")
        TreatmentReagent.objects.create(treatment=t, preparation=self.prep)
        r = self.client.get(reverse("writeoff"), {"preparation": self.prep.pk, "export": "xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"PK"))

    def test_duplicates_merge_moves_usages(self):
        dup = Preparation.objects.create(name=" хорус ", stock_code="777")
        t = Treatment.objects.create(date=date(2026, 5, 1), tank=10)
        TreatmentReagent.objects.create(treatment=t, preparation=dup, quantity=1)
        page = self.client.get(reverse("duplicates"))
        self.assertEqual(len(page.context["groups"]), 1)
        self.client.post(reverse("duplicates"), {"primary": self.prep.pk, "members": [self.prep.pk, dup.pk]})
        dup.refresh_from_db()
        self.prep.refresh_from_db()
        self.assertEqual(dup.merged_into, self.prep)
        self.assertEqual(self.prep.stock_code, "777")
        self.assertEqual(TreatmentReagent.objects.get().preparation, self.prep)
        self.assertEqual(len(self.client.get(reverse("duplicates")).context["groups"]), 0)

    def test_cannot_delete_inspection_with_treatments(self):
        i = Inspection.objects.create(date=date(2026, 5, 1), legacy_id=1)
        Treatment.objects.create(date=date(2026, 5, 2), inspection=i)
        self.client.post(reverse("inspection_delete", args=[i.pk]))
        self.assertTrue(Inspection.objects.filter(pk=i.pk).exists())

    def test_all_list_pages_open(self):
        for name in ("dashboard", "catalogs", "inspection_list", "treatment_list", "writeoff", "protection",
                     "duplicates", "tools", "audit", "inspection_new", "treatment_new"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


SYNTH = {
    "location": [{"ID": "1", "location": "КП-3", "loc_сode": "12"}],
    "place": [{"id": "5", "parent": "КП-3", "place": "Нижняя полка", "plan": "", "content": ""}],
    "flora": [{"ID": "1", "flora_name": "Роза", "flora_lat": "Rosa"}],
    "pest": [], "sickness": [], "physiology": [], "other": [],
    "farma": [{"ID": "1", "farma_name": "Хорус", "n_p": "25", "pref": "г", "clase": "", "use": "",
               "sklad_name": "", "sklad_pref": "", "farma_code": ""}],
    "person": [{"ID": "1", "surname": "Иванов", "name": "Иван", "parent": "Иванович", "post": ""}],
    "task": [], "protection": [],
    "inspection": [{"id": "2026051001", "data": "05/10/26 00:00:00", "place": "5", "location": "КП-3",
                    "flora": "Роза", "description": "тля", "done": "0", "inWork": "1", "Autor": "1",
                    "prev_insp": "", "reag1": "", "reag2": "", "reag3": "", "reag4": ""}],
    "treat": [
        {"count": "1", "data": "05/11/26 00:00:00", "flora": "роза ", "location": "КП-3", "person": "Иванов И.И.",
         "tank": "10", "reason": "2026051001", "Treat_type": "Обработка", "gasolin": "1", "write-down": "1",
         "reag1": "Хорус", "reag_count1": "25", "reag2": "Неизвестный", "reag_count2": "5",
         "reag3": "", "reag_count3": "0", "reag4": "", "reag_count4": "0"},
        {"count": "2", "data": "", "flora": "Кактус", "location": "Новый объект", "person": "Петров П.П.",
         "tank": "", "reason": "999", "Treat_type": "", "gasolin": "0", "write-down": "0",
         "reag1": "", "reag_count1": "", "reag2": "", "reag_count2": "", "reag3": "", "reag_count3": "",
         "reag4": "", "reag_count4": "", "task_insp": ""},
    ],
}


class ImporterTests(TestCase):
    def run_import(self):
        imp = Importer("fake.accdb")
        with mock.patch.object(accessdb, "read_table", side_effect=lambda path, t: SYNTH[t]):
            imp.run()
        return imp

    def test_import_links_and_placeholders(self):
        imp = self.run_import()
        self.assertEqual(Treatment.objects.count(), 2)
        t1 = Treatment.objects.get(legacy_id=1)
        self.assertEqual(t1.plant.name, "Роза")
        self.assertFalse(t1.plant.is_placeholder)
        self.assertEqual(t1.person.surname, "Иванов")
        self.assertEqual(t1.inspection.legacy_id, 2026051001)
        self.assertEqual(t1.reagents.count(), 2)
        self.assertTrue(all(r.written_off for r in t1.reagents.all()))
        self.assertTrue(Preparation.objects.get(name="Неизвестный").is_placeholder)
        self.assertTrue(Location.objects.get(name="Новый объект").is_placeholder)
        self.assertTrue(Person.objects.get(surname="Петров П.П.").is_placeholder)
        self.assertIsNone(Treatment.objects.get(legacy_id=2).date)
        self.assertIn("Растения, которых нет в справочнике (созданы как заглушки)", imp.report)

    def test_import_inspection_fields(self):
        self.run_import()
        i = Inspection.objects.get()
        self.assertEqual(i.date, date(2026, 5, 10))
        self.assertEqual(i.place.name, "Нижняя полка")
        self.assertTrue(i.in_work)
        self.assertFalse(i.done)
        self.assertEqual(i.author.surname, "Иванов")

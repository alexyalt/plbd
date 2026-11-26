from decimal import Decimal

from django.db import models


class Location(models.Model):
    name = models.CharField("Объект", max_length=200, unique=True)
    code = models.CharField("Код объекта", max_length=100, blank=True)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)
    is_placeholder = models.BooleanField("Создан при импорте (нет в справочнике)", default=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "объект"
        verbose_name_plural = "объекты"

    def __str__(self):
        return self.name


class Place(models.Model):
    location = models.ForeignKey(Location, verbose_name="Объект", null=True, blank=True,
                                 on_delete=models.PROTECT, related_name="places")
    name = models.CharField("Куртина / участок", max_length=300)
    plan = models.CharField("План", max_length=300, blank=True)
    content = models.TextField("Состав растений", blank=True)
    parent_raw = models.CharField(max_length=200, blank=True, editable=False)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["location__name", "name"]
        verbose_name = "куртина"
        verbose_name_plural = "куртины"

    def __str__(self):
        return f"{self.location or self.parent_raw} / {self.name}"


class Plant(models.Model):
    name = models.CharField("Растение", max_length=300, unique=True)
    latin = models.CharField("Латинское название", max_length=300, blank=True)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)
    is_placeholder = models.BooleanField("Создано при импорте (нет в справочнике)", default=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "растение"
        verbose_name_plural = "растения"

    def __str__(self):
        return self.name


class Cause(models.Model):
    PEST, DISEASE, PHYSIOLOGY, OTHER = "pest", "disease", "physiology", "other"
    KINDS = [(PEST, "Вредитель"), (DISEASE, "Болезнь"), (PHYSIOLOGY, "Физиология"), (OTHER, "Другое")]
    kind = models.CharField("Тип", max_length=12, choices=KINDS)
    name = models.CharField("Название", max_length=500)
    description = models.CharField("Латинское название / описание", max_length=1000, blank=True)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name = "причина"
        verbose_name_plural = "причины (вредители, болезни, физиология, другое)"

    def __str__(self):
        return self.name


class Preparation(models.Model):
    name = models.CharField("Препарат", max_length=300)
    dose_per_10l = models.DecimalField("Норма на 10 л", max_digits=12, decimal_places=3, null=True, blank=True)
    dose_raw = models.CharField(max_length=50, blank=True, editable=False)
    unit = models.CharField("Единица нормы", max_length=30, blank=True)
    kind = models.CharField("Класс", max_length=100, blank=True)
    usage = models.CharField("Способ применения", max_length=200, blank=True)
    active_substance = models.CharField("Действующее вещество", max_length=300, blank=True)
    stock_name = models.CharField("Наименование на складе", max_length=500, blank=True)
    stock_unit = models.CharField("Единица на складе", max_length=30, blank=True)
    stock_code = models.CharField("Код на складе", max_length=50, blank=True)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)
    is_placeholder = models.BooleanField("Создан при импорте (нет в справочнике)", default=False)
    merged_into = models.ForeignKey("self", null=True, blank=True, editable=False,
                                    on_delete=models.SET_NULL, related_name="merged_from")

    class Meta:
        ordering = ["name"]
        verbose_name = "препарат"
        verbose_name_plural = "препараты"

    def __str__(self):
        return self.name

    def quantity_for_tank(self, tank_liters):
        if self.dose_per_10l is None or tank_liters is None:
            return None
        return (Decimal(tank_liters) * self.dose_per_10l / 10).quantize(Decimal("0.01"))


class Person(models.Model):
    surname = models.CharField("Фамилия", max_length=100)
    name = models.CharField("Имя", max_length=100, blank=True)
    patronymic = models.CharField("Отчество", max_length=100, blank=True)
    post = models.CharField("Должность", max_length=200, blank=True)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)
    is_placeholder = models.BooleanField("Создан при импорте (нет в справочнике)", default=False)

    class Meta:
        ordering = ["surname", "name"]
        verbose_name = "сотрудник"
        verbose_name_plural = "сотрудники"

    def __str__(self):
        initials = "".join(f"{p[0]}." for p in (self.name, self.patronymic) if p)
        return f"{self.surname} {initials}".strip()


class TaskType(models.Model):
    name = models.CharField("Типовое назначение", max_length=500)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "типовое назначение"
        verbose_name_plural = "типовые назначения"

    def __str__(self):
        return self.name


class ProtectionRule(models.Model):
    week = models.IntegerField("Неделя года")
    phenology = models.CharField("Фенофаза", max_length=200)
    subject_id = models.IntegerField("ID растения (legacy)", null=True, blank=True)
    plant = models.ForeignKey(Plant, verbose_name="Растение", null=True, blank=True,
                              on_delete=models.SET_NULL)
    targets = models.TextField("Вредители / болезни")
    preparations = models.CharField("Препараты", max_length=500)
    legacy_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["week", "phenology"]
        verbose_name = "правило графика защиты"
        verbose_name_plural = "график защиты"

    def __str__(self):
        return f"нед. {self.week}: {self.phenology}"


class Inspection(models.Model):
    legacy_id = models.BigIntegerField("Номер акта", null=True, blank=True, unique=True)
    date = models.DateField("Дата осмотра", null=True, blank=True)
    location = models.ForeignKey(Location, verbose_name="Объект", null=True, blank=True,
                                 on_delete=models.PROTECT)
    place = models.ForeignKey(Place, verbose_name="Куртина", null=True, blank=True,
                              on_delete=models.SET_NULL)
    plant = models.ForeignKey(Plant, verbose_name="Растение", null=True, blank=True,
                              on_delete=models.PROTECT)
    inv = models.CharField("Инв. номер", max_length=100, blank=True)
    count = models.CharField("Количество", max_length=50, blank=True)
    description = models.TextField("Описание", blank=True)
    reason_kind = models.CharField("Тип причины", max_length=100, blank=True)
    reason_short = models.CharField("Причина (кратко)", max_length=500, blank=True)
    reason_text = models.TextField("Причина (полностью)", blank=True)
    prescription = models.TextField("Назначенные препараты / рекомендации", blank=True)
    task = models.TextField("Назначенные меры", blank=True)
    task_date = models.DateField("Срок выполнения", null=True, blank=True)
    done = models.BooleanField("Выполнено", default=False)
    in_work = models.BooleanField("В работе", default=False)
    author = models.ForeignKey(Person, verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="inspections")
    prev = models.ForeignKey("self", verbose_name="Предыдущий осмотр", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="next_inspections")
    reagents_raw = models.CharField(max_length=500, blank=True, editable=False)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "акт осмотра"
        verbose_name_plural = "акты осмотра"

    def __str__(self):
        return f"Осмотр {self.legacy_id or self.pk} от {self.date:%d.%m.%Y}" if self.date else f"Осмотр {self.legacy_id or self.pk}"


class Treatment(models.Model):
    TYPES = [("Обработка", "Обработка"), ("Полив", "Полив"), ("Внесение", "Внесение"),
             ("Доп задание", "Доп задание")]
    legacy_id = models.IntegerField("Номер (legacy)", null=True, blank=True, unique=True, editable=False)
    date = models.DateField("Дата", null=True, blank=True)
    location = models.ForeignKey(Location, verbose_name="Объект", null=True, blank=True,
                                 on_delete=models.PROTECT)
    plant = models.ForeignKey(Plant, verbose_name="Растение", null=True, blank=True,
                              on_delete=models.PROTECT)
    person = models.ForeignKey(Person, verbose_name="Садовник", null=True, blank=True,
                               on_delete=models.PROTECT, related_name="treatments")
    inspection = models.ForeignKey(Inspection, verbose_name="Осмотр", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="treatments")
    inspection_legacy_id = models.BigIntegerField(null=True, blank=True, editable=False)
    tank = models.IntegerField("Объём бака, л", null=True, blank=True)
    treat_type = models.CharField("Тип", max_length=30, blank=True, choices=TYPES)
    gasoline = models.BooleanField("Бензин (опрыскиватель)", default=False)
    result = models.CharField("Результат", max_length=500, blank=True)
    task_text = models.TextField("Задание", blank=True)
    written_off = models.BooleanField("Списано", default=False)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "обработка"
        verbose_name_plural = "обработки"

    def __str__(self):
        return f"Обработка {self.legacy_id or self.pk} от {self.date:%d.%m.%Y}" if self.date else f"Обработка {self.legacy_id or self.pk}"


class TreatmentReagent(models.Model):
    treatment = models.ForeignKey(Treatment, on_delete=models.CASCADE, related_name="reagents")
    preparation = models.ForeignKey(Preparation, verbose_name="Препарат", on_delete=models.PROTECT,
                                    related_name="usages")
    quantity = models.DecimalField("Расход", max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "препарат обработки"
        verbose_name_plural = "препараты обработки"

    def __str__(self):
        return f"{self.preparation}: {self.quantity}"

    def save(self, *args, **kwargs):
        if self.quantity is None:
            self.quantity = self.preparation.quantity_for_tank(self.treatment.tank)
        super().save(*args, **kwargs)

from django import forms

from .models import Inspection, Preparation, Treatment, TreatmentReagent
from django.forms import inlineformset_factory

DATE = lambda: forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class InspectionForm(forms.ModelForm):
    class Meta:
        model = Inspection
        exclude = ["legacy_id", "reagents_raw"]
        widgets = {
            "date": DATE(), "task_date": DATE(),
            "description": forms.Textarea(attrs={"rows": 3}),
            "reason_text": forms.Textarea(attrs={"rows": 2}),
            "prescription": forms.Textarea(attrs={"rows": 3}),
            "task": forms.Textarea(attrs={"rows": 2}),
        }


class TreatmentForm(forms.ModelForm):
    class Meta:
        model = Treatment
        exclude = ["legacy_id", "inspection_legacy_id"]
        widgets = {"date": DATE(), "task_text": forms.Textarea(attrs={"rows": 2})}


class ReagentForm(forms.ModelForm):
    class Meta:
        model = TreatmentReagent
        fields = ["preparation", "quantity", "written_off"]


ReagentFormSet = inlineformset_factory(
    Treatment, TreatmentReagent, form=ReagentForm, extra=3, max_num=4, validate_max=True, can_delete=True)


class WriteoffFilter(forms.Form):
    preparation = forms.ModelChoiceField(Preparation.objects.filter(merged_into__isnull=True),
                                         label="Препарат", required=False)
    date_from = forms.DateField(label="С даты", required=False, widget=DATE())
    date_to = forms.DateField(label="По дату", required=False, widget=DATE())

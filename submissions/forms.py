from django import forms

from .models import Submission


class ProgramFilterForm(forms.Form):
    """Фильтр программы. Неизвестная страна отбрасывается как невалидное значение."""

    q = forms.CharField(label="Поиск", required=False, max_length=100)
    country = forms.ChoiceField(label="Страна", required=False)

    def __init__(self, data, countries):
        super().__init__(data)
        self.fields["country"].choices = [("", "Все страны")] + [(c, c) for c in countries]

    def filters(self):
        """Значения фильтров; невалидные поля считаются незаданными."""
        self.is_valid()
        return {
            "query": self.cleaned_data.get("q", ""),
            "country": self.cleaned_data.get("country", ""),
        }


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("title", "abstract", "file")
        widgets = {"abstract": forms.Textarea(attrs={"rows": 8})}

from django import forms

from .services import MAX_SCORE, MIN_SCORE


class ReviewForm(forms.Form):
    score = forms.TypedChoiceField(
        label="Оценка",
        coerce=int,
        choices=[("", "Выберите оценку")] + [(n, f"{n}") for n in range(MIN_SCORE, MAX_SCORE + 1)],
        empty_value=None,
    )
    comment = forms.CharField(
        label="Комментарий", required=False, widget=forms.Textarea(attrs={"rows": 6})
    )

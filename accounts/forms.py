from django import forms
from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.models import Group

from . import roles
from .models import User


class SignUpForm(BaseUserCreationForm):
    """Самостоятельная регистрация участника: email, имя и пароль."""

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"]
        # Уникальность на уровне БД чувствительна к регистру локальной части адреса,
        # поэтому дополнительно не пускаем дубли, отличающиеся только регистром.
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            user.groups.add(Group.objects.get(name=roles.PARTICIPANT))
        return user

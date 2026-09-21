import re

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.db import models


class UserManager(DjangoUserManager):
    """Менеджер пользователей, где идентификатор для входа — email, а не username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email обязателен.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("У суперпользователя должны быть is_staff=True и is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Пользователь сайта. Вход по email; username не используется."""

    username = None
    email = models.EmailField("email", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    def __str__(self):
        return self.email


def validate_orcid(value):
    """Проверяет формат ORCID (0000-0000-0000-000X) и контрольную цифру (ISO 7064 mod 11-2)."""
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", value):
        raise ValidationError(
            "ORCID должен иметь вид 0000-0000-0000-0000 (последний символ может быть X)."
        )

    digits = value.replace("-", "")
    total = 0
    for char in digits[:-1]:
        total = (total + int(char)) * 2
    check = (12 - total % 11) % 11
    expected = "X" if check == 10 else str(check)
    if digits[-1] != expected:
        raise ValidationError("Неверная контрольная цифра ORCID.")


class Profile(models.Model):
    """Данные участника, не относящиеся к аутентификации.

    Человек существует в системе один раз; его участия в конференциях — отдельные записи
    (заявки, регистрации), поэтому история участий строится выборкой по профилю.
    `legacy_id` хранит идентификатор из старой системы (Drupal) для идемпотентного импорта.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile", verbose_name="пользователь"
    )
    affiliation = models.CharField("организация", max_length=255, blank=True)
    country = models.CharField("страна", max_length=100, blank=True)
    orcid = models.CharField("ORCID", max_length=19, blank=True, validators=[validate_orcid])
    legacy_id = models.CharField(
        "идентификатор в старой системе", max_length=64, unique=True, null=True, blank=True
    )

    class Meta:
        verbose_name = "профиль"
        verbose_name_plural = "профили"

    def __str__(self):
        return f"Профиль {self.user.email}"

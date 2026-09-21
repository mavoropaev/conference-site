from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from accounts.models import Profile
from conferences.models import Conference

MAX_FILE_SIZE_MB = 10


def validate_file_size(uploaded_file):
    if uploaded_file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"Файл больше {MAX_FILE_SIZE_MB} МБ.")


def submission_file_path(instance, filename):
    """Файлы раскладываются по конференциям: submissions/<slug конференции>/<имя файла>."""
    return f"submissions/{instance.conference.slug}/{filename}"


class Submission(models.Model):
    """Заявка на доклад."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SUBMITTED = "submitted", "Подана"
        ACCEPTED = "accepted", "Принята"
        REJECTED = "rejected", "Отклонена"

    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="конференция",
    )
    author = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="автор",
    )
    title = models.CharField("название", max_length=255)
    abstract = models.TextField("аннотация")
    file = models.FileField(
        "файл",
        upload_to=submission_file_path,
        blank=True,
        validators=[FileExtensionValidator(["pdf", "doc", "docx"]), validate_file_size],
    )
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField("создана", auto_now_add=True)
    updated_at = models.DateTimeField("изменена", auto_now=True)

    class Meta:
        verbose_name = "заявка на доклад"
        verbose_name_plural = "заявки на доклады"
        ordering = ["-created_at"]
        permissions = [
            ("decide_submission", "Может принимать и отклонять заявки"),
        ]
        indexes = [
            # Список докладов конференции с фильтром по статусу.
            models.Index(fields=["conference", "status"]),
            models.Index(fields=["author"]),
        ]

    def __str__(self):
        return self.title


class Registration(models.Model):
    """Регистрация участника на конференцию."""

    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name="конференция",
    )
    participant = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name="участник",
    )
    created_at = models.DateTimeField("зарегистрирован", auto_now_add=True)

    class Meta:
        verbose_name = "регистрация"
        verbose_name_plural = "регистрации"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "participant"],
                name="unique_registration_per_conference",
            ),
        ]

    def __str__(self):
        return f"{self.participant} → {self.conference}"

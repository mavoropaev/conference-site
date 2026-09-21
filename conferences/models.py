from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models import F, Q


class StageTransitionError(Exception):
    """Недопустимый переход между этапами конференции."""


class Stage(models.TextChoices):
    """Этапы конференции. Порядок объявления задаёт порядок прохождения."""

    SUBMISSION = "submission", "Приём заявок"
    REVIEW = "review", "Рецензирование"
    REGISTRATION = "registration", "Регистрация"
    ONGOING = "ongoing", "Проведение"
    FINISHED = "finished", "Завершена"


class Conference(models.Model):
    """Конференция. Этап меняется только через `advance()` и `revert()`."""

    title = models.CharField("название", max_length=255)
    slug = models.SlugField("слаг", unique=True)
    description = models.TextField("описание", blank=True)
    location = models.CharField("место проведения", max_length=255, blank=True)
    start_date = models.DateField("дата начала")
    end_date = models.DateField("дата окончания")
    stage = models.CharField("этап", max_length=20, choices=Stage.choices, default=Stage.SUBMISSION)
    created_at = models.DateTimeField("создана", auto_now_add=True)

    class Meta:
        verbose_name = "конференция"
        verbose_name_plural = "конференции"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="conference_end_not_before_start",
            ),
        ]
        permissions = [
            ("manage_stage", "Может переводить конференцию на следующий этап"),
            ("revert_stage", "Может возвращать конференцию на предыдущий этап"),
        ]

    def __str__(self):
        return self.title

    # Что разрешено на текущем этапе. Вьюхи и формы опираются на эти свойства,
    # а не сравнивают этап напрямую.

    @property
    def accepts_submissions(self):
        return self.stage == Stage.SUBMISSION

    @property
    def reviews_open(self):
        return self.stage == Stage.REVIEW

    @property
    def registration_open(self):
        return self.stage == Stage.REGISTRATION

    def advance(self, by, reason=""):
        """Перевести на следующий этап. Нужно право `manage_stage`."""
        if not by.has_perm("conferences.manage_stage"):
            raise PermissionDenied("Нет права переводить конференцию на следующий этап.")
        return self._move(by=by, step=1, reason=reason)

    def revert(self, by, reason):
        """Вернуть на предыдущий этап. Нужно право `revert_stage` и указанная причина."""
        if not by.has_perm("conferences.revert_stage"):
            raise PermissionDenied("Нет права возвращать конференцию на предыдущий этап.")
        if not reason or not reason.strip():
            raise StageTransitionError("Для возврата на предыдущий этап нужно указать причину.")
        return self._move(by=by, step=-1, reason=reason.strip())

    @transaction.atomic
    def _move(self, by, step, reason):
        # Блокируем строку, чтобы два одновременных перехода не сдвинули этап дважды.
        current = Conference.objects.select_for_update().get(pk=self.pk)
        stages = Stage.values
        index = stages.index(current.stage) + step

        if index < 0:
            raise StageTransitionError("Конференция уже на первом этапе: возвращаться некуда.")
        if index >= len(stages):
            raise StageTransitionError("Конференция уже завершена: дальше переходить некуда.")

        old_stage, new_stage = current.stage, stages[index]
        current.stage = new_stage
        current.save(update_fields=["stage"])
        self.stage = new_stage

        return StageTransition.objects.create(
            conference=self,
            from_stage=old_stage,
            to_stage=new_stage,
            changed_by=by,
            reason=reason,
        )


class StageTransition(models.Model):
    """Журнал переходов между этапами: кто, когда, откуда и куда."""

    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name="transitions",
        verbose_name="конференция",
    )
    from_stage = models.CharField("с этапа", max_length=20, choices=Stage.choices)
    to_stage = models.CharField("на этап", max_length=20, choices=Stage.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name="кто изменил",
    )
    reason = models.TextField("причина", blank=True)
    created_at = models.DateTimeField("когда", auto_now_add=True)

    class Meta:
        verbose_name = "переход между этапами"
        verbose_name_plural = "переходы между этапами"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["conference", "-created_at"])]

    def __str__(self):
        return f"{self.conference}: {self.from_stage} → {self.to_stage}"

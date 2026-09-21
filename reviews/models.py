from django.conf import settings
from django.db import models
from django.db.models import Q

from submissions.models import Submission


class Review(models.Model):
    """Рецензия на заявку. Запись создаётся при назначении рецензента, оценка ставится позже."""

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="заявка",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="рецензент",
    )
    score = models.PositiveSmallIntegerField("оценка", null=True, blank=True)
    comment = models.TextField("комментарий", blank=True)
    created_at = models.DateTimeField("назначена", auto_now_add=True)
    updated_at = models.DateTimeField("изменена", auto_now=True)

    class Meta:
        verbose_name = "рецензия"
        verbose_name_plural = "рецензии"
        ordering = ["-created_at"]
        permissions = [
            ("assign_reviewer", "Может назначать рецензентов на заявки"),
        ]
        constraints = [
            # Один рецензент — одна рецензия на заявку.
            models.UniqueConstraint(
                fields=["submission", "reviewer"], name="unique_review_per_reviewer"
            ),
            # Оценка либо ещё не поставлена, либо от 1 до 5.
            models.CheckConstraint(
                condition=Q(score__isnull=True) | Q(score__gte=1, score__lte=5),
                name="review_score_between_1_and_5",
            ),
        ]
        indexes = [
            # «Мои рецензии» у рецензента.
            models.Index(fields=["reviewer"]),
        ]

    def __str__(self):
        return f"Рецензия {self.reviewer} на «{self.submission}»"

    @property
    def is_completed(self):
        return self.score is not None

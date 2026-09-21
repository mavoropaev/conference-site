"""Правила рецензирования. Вьюхи только вызывают эти функции."""

from django.core.exceptions import PermissionDenied

from accounts import roles
from submissions.models import Submission

from .models import Review

MIN_SCORE, MAX_SCORE = 1, 5


class ReviewError(Exception):
    """Действие с рецензией сейчас недопустимо; текст показывается пользователю."""


def assign_reviewer(submission, reviewer, by):
    """Назначает рецензента на заявку. Нужно право `reviews.assign_reviewer`."""
    if not by.has_perm("reviews.assign_reviewer"):
        raise PermissionDenied("Нет права назначать рецензентов.")
    if not submission.conference.reviews_open:
        raise ReviewError("Рецензентов можно назначать только на этапе рецензирования.")
    if submission.status != Submission.Status.SUBMITTED:
        raise ReviewError("Рецензента можно назначить только на поданную заявку.")
    if not reviewer.groups.filter(name=roles.REVIEWER).exists():
        raise ReviewError("Этот пользователь не входит в роль «Рецензент».")
    if submission.author.user_id == reviewer.pk:
        raise ReviewError("Автор не может рецензировать собственную заявку.")

    review, created = Review.objects.get_or_create(submission=submission, reviewer=reviewer)
    if not created:
        raise ReviewError("Этот рецензент уже назначен на заявку.")
    return review


def save_review(review, score, comment=""):
    """Сохраняет оценку и комментарий, пока идёт этап рецензирования."""
    if not review.submission.conference.reviews_open:
        raise ReviewError("Приём рецензий закрыт: этап рецензирования не идёт.")
    if score not in range(MIN_SCORE, MAX_SCORE + 1):
        raise ReviewError(f"Оценка должна быть от {MIN_SCORE} до {MAX_SCORE}.")

    review.score = score
    review.comment = comment
    review.save(update_fields=["score", "comment", "updated_at"])
    return review

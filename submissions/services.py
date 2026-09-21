"""Правила работы с заявками. Вьюхи только вызывают эти функции и не знают правил."""

from django.core.exceptions import PermissionDenied

from .models import Submission


class SubmissionError(Exception):
    """Действие с заявкой сейчас недопустимо; текст исключения показывается пользователю."""


EDITABLE_STATUSES = (Submission.Status.DRAFT, Submission.Status.SUBMITTED)


def ensure_conference_accepts(conference):
    if not conference.accepts_submissions:
        raise SubmissionError("Приём заявок на эту конференцию закрыт.")


def can_edit(submission):
    return submission.conference.accepts_submissions and submission.status in EDITABLE_STATUSES


def ensure_editable(submission):
    ensure_conference_accepts(submission.conference)
    if submission.status not in EDITABLE_STATUSES:
        raise SubmissionError("Заявка уже рассмотрена и не может быть изменена.")


def create_submission(form, conference, author):
    """Создаёт черновик из валидной формы."""
    ensure_conference_accepts(conference)
    submission = form.save(commit=False)
    submission.conference = conference
    submission.author = author
    submission.status = Submission.Status.DRAFT
    submission.save()
    return submission


def update_submission(form):
    """Сохраняет изменения валидной формы, если заявку ещё можно менять."""
    ensure_editable(form.instance)
    return form.save()


def submit(submission):
    """Отправляет черновик на рассмотрение."""
    ensure_editable(submission)
    if submission.status == Submission.Status.SUBMITTED:
        raise SubmissionError("Заявка уже отправлена.")
    submission.status = Submission.Status.SUBMITTED
    submission.save(update_fields=["status", "updated_at"])
    return submission


DECISIONS = (Submission.Status.ACCEPTED, Submission.Status.REJECTED)
DECIDABLE_STATUSES = (Submission.Status.SUBMITTED, *DECISIONS)


def decide(submission, decision, by):
    """Принимает или отклоняет заявку. Нужно право `decide_submission`, идёт рецензирование.

    Решение можно пересмотреть (принята ↔ отклонена), пока этап рецензирования не закончился.
    """
    if not by.has_perm("submissions.decide_submission"):
        raise PermissionDenied("Нет права принимать решения по заявкам.")
    if decision not in DECISIONS:
        raise SubmissionError("Неизвестное решение.")
    if not submission.conference.reviews_open:
        raise SubmissionError("Решения принимаются только на этапе рецензирования.")
    if submission.status not in DECIDABLE_STATUSES:
        raise SubmissionError("Черновик нельзя принять или отклонить: автор его ещё не отправил.")

    submission.status = decision
    submission.save(update_fields=["status", "updated_at"])
    return submission

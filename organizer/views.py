"""Панель оргкомитета: этапы, заявки, рецензенты, решения."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts import roles
from conferences.models import Conference, Stage, StageTransitionError
from reviews import services as review_services
from reviews.services import ReviewError
from submissions import services as submission_services
from submissions.models import Submission
from submissions.services import SubmissionError

User = get_user_model()

# Ошибки бизнес-правил, которые показываются пользователю внутри панели.
ACTION_ERRORS = (StageTransitionError, ReviewError, SubmissionError, PermissionDenied)

DECISIONS = {
    "accept": Submission.Status.ACCEPTED,
    "reject": Submission.Status.REJECTED,
}


def organizer_only(view):
    """Нужен вход и право переводить конференцию по этапам (роль «Оргкомитет»)."""
    return login_required(
        permission_required("conferences.manage_stage", raise_exception=True)(view)
    )


def _panel_url(conference):
    return reverse("organizer_panel", args=[conference.slug])


def _rows(conference, pk=None):
    """Отправленные заявки с числом рецензий и средней оценкой; черновики не показываются."""
    submissions = (
        Submission.objects.filter(conference=conference)
        .exclude(status=Submission.Status.DRAFT)
        .select_related("author__user", "conference")
        .prefetch_related("reviews")
        .annotate(
            reviews_total=Count("reviews", distinct=True),
            reviews_done=Count("reviews", filter=Q(reviews__score__isnull=False), distinct=True),
            average_score=Avg("reviews__score"),
        )
        .order_by("title")
    )
    if pk is not None:
        submissions = submissions.filter(pk=pk)

    reviewers = list(
        User.objects.filter(groups__name=roles.REVIEWER).order_by("last_name", "email")
    )
    rows = list(submissions)
    for row in rows:
        assigned = {review.reviewer_id for review in row.reviews.all()}
        row.available_reviewers = [
            u for u in reviewers if u.pk not in assigned and u.pk != row.author.user_id
        ]
    return rows


def _stage_context(conference, error=None):
    stages = Stage.values
    current = stages.index(conference.stage)
    steps = [
        {"label": label, "state": "done" if i < current else "current" if i == current else "todo"}
        for i, (_, label) in enumerate(Stage.choices)
    ]
    return {
        "conference": conference,
        "steps": steps,
        "transitions": conference.transitions.select_related("changed_by")[:10],
        "error": error,
    }


def _stage_response(request, conference, error=None, ok=None):
    if not request.htmx:
        (messages.error if error else messages.success)(request, error or ok)
        return redirect(_panel_url(conference))
    context = _stage_context(conference, error) | {"rows": _rows(conference)}
    return render(request, "organizer/_stage_update.html", context)


def _row_response(request, submission, error=None, ok=None):
    conference = submission.conference
    if not request.htmx:
        (messages.error if error else messages.success)(request, error or ok)
        return redirect(_panel_url(conference))
    context = {
        "row": _rows(conference, pk=submission.pk)[0],
        "conference": conference,
        "error": error,
    }
    return render(request, "organizer/_row.html", context)


@organizer_only
def dashboard(request):
    conferences = Conference.objects.annotate(
        submitted_count=Count("submissions", filter=~Q(submissions__status="draft"))
    )
    return render(request, "organizer/dashboard.html", {"conferences": conferences})


@organizer_only
def panel(request, slug):
    conference = get_object_or_404(Conference, slug=slug)
    context = _stage_context(conference) | {"rows": _rows(conference)}
    return render(request, "organizer/panel.html", context)


@organizer_only
@require_POST
def stage_advance(request, slug):
    conference = get_object_or_404(Conference, slug=slug)
    try:
        conference.advance(by=request.user)
    except ACTION_ERRORS as exc:
        return _stage_response(request, conference, error=str(exc))
    return _stage_response(request, conference, ok=f"Этап: {conference.get_stage_display()}.")


@organizer_only
@require_POST
def stage_revert(request, slug):
    conference = get_object_or_404(Conference, slug=slug)
    try:
        conference.revert(by=request.user, reason=request.POST.get("reason", ""))
    except ACTION_ERRORS as exc:
        return _stage_response(request, conference, error=str(exc))
    return _stage_response(
        request, conference, ok=f"Возврат на этап: {conference.get_stage_display()}."
    )


def _submission_for_action(pk):
    return get_object_or_404(Submission.objects.select_related("conference", "author__user"), pk=pk)


@organizer_only
@require_POST
def assign_reviewer(request, pk):
    submission = _submission_for_action(pk)
    reviewer_id = request.POST.get("reviewer", "")
    reviewer = User.objects.filter(pk=reviewer_id).first() if reviewer_id.isdigit() else None
    if reviewer is None:
        return _row_response(request, submission, error="Выберите рецензента.")
    try:
        review_services.assign_reviewer(submission, reviewer, by=request.user)
    except ACTION_ERRORS as exc:
        return _row_response(request, submission, error=str(exc))
    return _row_response(request, submission, ok=f"Рецензент назначен: {reviewer.email}.")


@organizer_only
@require_POST
def decide(request, pk):
    submission = _submission_for_action(pk)
    decision = DECISIONS.get(request.POST.get("decision"))
    try:
        submission_services.decide(submission, decision, by=request.user)
    except ACTION_ERRORS as exc:
        return _row_response(request, submission, error=str(exc))
    return _row_response(request, submission, ok=f"Решение: {submission.get_status_display()}.")

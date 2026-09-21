from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect

from conferences.models import Conference, Stage

from . import services
from .forms import SubmissionForm
from .models import Submission
from .services import SubmissionError

# Каждое представление отдаёт фрагмент при запросе HTMX и полную страницу без него,
# поэтому интерфейс работает и с выключенным JavaScript.


def _own_submission(request, pk):
    """Заявка текущего пользователя. Чужая — 404, чтобы не раскрывать её существование."""
    return get_object_or_404(
        Submission.objects.select_related("conference"), pk=pk, author=request.user.profile
    )


def _render_card(request, submission, error=None):
    context = {
        "submission": submission,
        "editable": services.can_edit(submission),
        "error": error,
    }
    return render(request, "submissions/_card.html", context)


def _refuse(request, message, url):
    """Отказ: сообщение и переход на страницу `url` (для HTMX — полный переход)."""
    messages.error(request, message)
    if request.htmx:
        return HttpResponseClientRedirect(url)
    return redirect(url)


@login_required
def submission_list(request):
    submissions = Submission.objects.filter(author=request.user.profile).select_related(
        "conference"
    )
    open_conferences = Conference.objects.filter(stage=Stage.SUBMISSION)
    return render(
        request,
        "submissions/list.html",
        {"submissions": submissions, "open_conferences": open_conferences},
    )


@login_required
def submission_detail(request, pk):
    submission = _own_submission(request, pk)
    if request.htmx:
        return _render_card(request, submission)
    return render(
        request,
        "submissions/detail.html",
        {"submission": submission, "editable": services.can_edit(submission)},
    )


@login_required
def submission_create(request, slug):
    conference = get_object_or_404(Conference, slug=slug)
    conference_url = reverse("conference_detail", args=[slug])
    try:
        services.ensure_conference_accepts(conference)
    except SubmissionError as exc:
        return _refuse(request, str(exc), conference_url)

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = services.create_submission(form, conference, request.user.profile)
            url = reverse("submission_detail", args=[submission.pk])
            if request.htmx:
                response = _render_card(request, submission)
                response["HX-Push-Url"] = url
                return response
            messages.success(request, "Заявка сохранена как черновик.")
            return redirect(url)
    else:
        form = SubmissionForm()

    template = "submissions/_form.html" if request.htmx else "submissions/form.html"
    context = {
        "form": form,
        "conference": conference,
        "action": reverse("submission_create", args=[slug]),
    }
    return render(request, template, context)


@login_required
def submission_edit(request, pk):
    submission = _own_submission(request, pk)
    detail_url = reverse("submission_detail", args=[pk])
    try:
        services.ensure_editable(submission)
    except SubmissionError as exc:
        if request.htmx:
            return _render_card(request, submission, error=str(exc))
        return _refuse(request, str(exc), detail_url)

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES, instance=submission)
        if form.is_valid():
            services.update_submission(form)
            if request.htmx:
                return _render_card(request, submission)
            messages.success(request, "Изменения сохранены.")
            return redirect(detail_url)
    else:
        form = SubmissionForm(instance=submission)

    template = "submissions/_form.html" if request.htmx else "submissions/form.html"
    context = {
        "form": form,
        "conference": submission.conference,
        "submission": submission,
        "action": reverse("submission_edit", args=[pk]),
    }
    return render(request, template, context)


@login_required
@require_POST
def submission_submit(request, pk):
    submission = _own_submission(request, pk)
    detail_url = reverse("submission_detail", args=[pk])
    try:
        services.submit(submission)
    except SubmissionError as exc:
        if request.htmx:
            return _render_card(request, submission, error=str(exc))
        return _refuse(request, str(exc), detail_url)

    if request.htmx:
        return _render_card(request, submission)
    messages.success(request, "Заявка отправлена на рассмотрение.")
    return redirect(detail_url)

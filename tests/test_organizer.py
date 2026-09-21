"""Панель оргкомитета: доступ, смена этапов, назначение рецензентов, решения."""

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from accounts import roles
from conferences.models import Stage, StageTransition
from reviews.models import Review
from submissions import services
from submissions.models import Submission
from submissions.services import SubmissionError

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def organizer(make_user):
    return make_user("org@example.com", groups=[roles.ORGANIZER])


@pytest.fixture
def org_client(client, organizer):
    client.force_login(organizer)
    return client


@pytest.fixture
def conference(make_conference):
    return make_conference(slug="org-conf", title="Конференция оргкомитета")


@pytest.fixture
def make_submission(conference, make_user):
    counter = {"n": 0}

    def _make(status=Submission.Status.SUBMITTED, title="Доклад", conf=None):
        counter["n"] += 1
        author = make_user(
            f"author{counter['n']}@example.com", first_name="Анна", last_name="Автор"
        )
        return Submission.objects.create(
            conference=conf or conference,
            author=author.profile,
            title=title,
            abstract="Текст",
            status=status,
        )

    return _make


@pytest.fixture
def reviewer(make_user):
    return make_user(
        "rev@example.com", groups=[roles.REVIEWER], first_name="Роман", last_name="Рецензентов"
    )


def panel_url(conference):
    return reverse("organizer_panel", args=[conference.slug])


# --- доступ ---------------------------------------------------------------


def test_anonymous_is_redirected_to_login(client, conference):
    for url in (reverse("organizer_dashboard"), panel_url(conference)):
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("login") in response["Location"]


@pytest.mark.parametrize("role", [roles.PARTICIPANT, roles.REVIEWER])
def test_non_organizers_get_403(client, make_user, conference, role):
    client.force_login(make_user("x@example.com", groups=[role]))

    assert client.get(reverse("organizer_dashboard")).status_code == 403
    assert client.get(panel_url(conference)).status_code == 403
    assert client.post(reverse("organizer_advance", args=[conference.slug])).status_code == 403


def test_non_organizer_cannot_decide_or_assign(client, make_user, make_submission, conference):
    conference.stage = Stage.REVIEW
    conference.save()
    submission = make_submission()
    client.force_login(make_user("rev@example.com", groups=[roles.REVIEWER]))

    assert (
        client.post(
            reverse("organizer_decide", args=[submission.pk]), {"decision": "accept"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("organizer_assign", args=[submission.pk]), {"reviewer": "1"}
        ).status_code
        == 403
    )
    submission.refresh_from_db()
    assert submission.status == Submission.Status.SUBMITTED


def test_dashboard_lists_conferences_with_submission_counts(
    org_client, conference, make_submission
):
    make_submission()
    make_submission(status=Submission.Status.DRAFT)

    content = org_client.get(reverse("organizer_dashboard")).content.decode()

    assert "Конференция оргкомитета" in content
    assert "Отправленных заявок: 1" in content


def test_navigation_link_only_for_organizers(client, organizer, make_user):
    client.force_login(organizer)
    organizer_page = client.get(reverse("home")).content.decode()
    client.force_login(make_user("part@example.com", groups=[roles.PARTICIPANT]))
    participant_page = client.get(reverse("home")).content.decode()

    assert "Панель оргкомитета" in organizer_page
    assert "Панель оргкомитета" not in participant_page


# --- панель ---------------------------------------------------------------


def test_panel_hides_drafts_and_shows_authors(org_client, conference, make_submission):
    make_submission(title="Отправленный")
    make_submission(status=Submission.Status.DRAFT, title="Скрытый черновик")

    content = org_client.get(panel_url(conference)).content.decode()

    assert "Отправленный" in content
    assert "Анна Автор" in content
    assert "Скрытый черновик" not in content


def test_panel_shows_review_statistics(org_client, conference, make_submission, make_user):
    conference.stage = Stage.REVIEW
    conference.save()
    submission = make_submission()
    Review.objects.create(submission=submission, reviewer=make_user("r1@example.com"), score=4)
    Review.objects.create(submission=submission, reviewer=make_user("r2@example.com"), score=5)
    Review.objects.create(submission=submission, reviewer=make_user("r3@example.com"))

    content = org_client.get(panel_url(conference)).content.decode()

    assert "Рецензий: 2 из 3" in content
    assert "средняя оценка 4,5" in content or "средняя оценка 4.5" in content


def test_panel_query_count_does_not_grow_with_submissions(
    org_client, conference, make_submission, django_assert_max_num_queries
):
    conference.stage = Stage.REVIEW
    conference.save()
    for _ in range(8):
        make_submission()

    with django_assert_max_num_queries(12):
        org_client.get(panel_url(conference))


# --- этапы ----------------------------------------------------------------


def test_advance_moves_stage_and_writes_journal(org_client, organizer, conference):
    response = org_client.post(reverse("organizer_advance", args=[conference.slug]), **HTMX)

    conference.refresh_from_db()
    assert conference.stage == Stage.REVIEW
    assert StageTransition.objects.get().changed_by == organizer
    assert "Рецензирование" in response.content.decode()


def test_advance_response_also_refreshes_submissions_out_of_band(
    org_client, conference, make_submission
):
    make_submission()

    response = org_client.post(reverse("organizer_advance", args=[conference.slug]), **HTMX)

    content = response.content.decode()
    assert 'id="stage-block"' in content
    assert 'hx-swap-oob="true"' in content
    assert "Принять" in content  # на этапе рецензирования появились действия над заявкой


def test_advance_without_htmx_redirects_back_to_panel(org_client, conference):
    response = org_client.post(reverse("organizer_advance", args=[conference.slug]))

    assert response.status_code == 302
    assert response["Location"] == panel_url(conference)


def test_advance_from_finished_shows_error_and_keeps_stage(org_client, make_conference):
    finished = make_conference(slug="done", stage=Stage.FINISHED)

    response = org_client.post(reverse("organizer_advance", args=[finished.slug]), **HTMX)

    finished.refresh_from_db()
    assert finished.stage == Stage.FINISHED
    assert "уже завершена" in response.content.decode()


def test_revert_requires_reason(org_client, make_conference):
    reviewing = make_conference(slug="rev", stage=Stage.REVIEW)

    response = org_client.post(
        reverse("organizer_revert", args=[reviewing.slug]), {"reason": " "}, **HTMX
    )

    reviewing.refresh_from_db()
    assert reviewing.stage == Stage.REVIEW
    assert "нужно указать причину" in response.content.decode()


def test_revert_with_reason_goes_back_and_logs_reason(org_client, make_conference):
    reviewing = make_conference(slug="rev", stage=Stage.REVIEW)

    org_client.post(
        reverse("organizer_revert", args=[reviewing.slug]), {"reason": "Ошибка в сроках"}, **HTMX
    )

    reviewing.refresh_from_db()
    assert reviewing.stage == Stage.SUBMISSION
    assert StageTransition.objects.get().reason == "Ошибка в сроках"


def test_organizer_without_revert_permission_is_refused(client, make_user, make_conference):
    limited = make_user("lim@example.com", perms=["manage_stage"])
    reviewing = make_conference(slug="rev", stage=Stage.REVIEW)
    client.force_login(limited)

    response = client.post(
        reverse("organizer_revert", args=[reviewing.slug]), {"reason": "нужно"}, **HTMX
    )

    reviewing.refresh_from_db()
    assert reviewing.stage == Stage.REVIEW
    assert "Нет права" in response.content.decode()
    assert "Причина возврата" not in client.get(panel_url(reviewing)).content.decode()


# --- назначение рецензентов ----------------------------------------------


@pytest.fixture
def reviewing(conference):
    conference.stage = Stage.REVIEW
    conference.save()
    return conference


def test_assign_reviewer_creates_review_and_returns_updated_row(
    org_client, reviewing, make_submission, reviewer
):
    submission = make_submission()

    response = org_client.post(
        reverse("organizer_assign", args=[submission.pk]), {"reviewer": reviewer.pk}, **HTMX
    )

    assert Review.objects.get().reviewer == reviewer
    assert f'id="row-{submission.pk}"' in response.content.decode()
    assert "<html" not in response.content.decode()


def test_assigned_reviewer_disappears_from_options(
    org_client, reviewing, make_submission, reviewer
):
    submission = make_submission()
    Review.objects.create(submission=submission, reviewer=reviewer)

    content = org_client.get(panel_url(reviewing)).content.decode()

    assert "Рецензентов" not in content
    assert 'name="reviewer"' not in content


def test_assign_without_choice_shows_error(org_client, reviewing, make_submission, reviewer):
    submission = make_submission()

    response = org_client.post(
        reverse("organizer_assign", args=[submission.pk]), {"reviewer": ""}, **HTMX
    )

    assert "Выберите рецензента" in response.content.decode()
    assert not Review.objects.exists()


def test_assign_non_reviewer_is_refused(org_client, reviewing, make_submission, make_user):
    submission = make_submission()
    participant = make_user("part@example.com", groups=[roles.PARTICIPANT])

    response = org_client.post(
        reverse("organizer_assign", args=[submission.pk]), {"reviewer": participant.pk}, **HTMX
    )

    assert "Рецензент" in response.content.decode()
    assert not Review.objects.exists()


def test_assign_options_exclude_the_author(org_client, reviewing, make_submission):
    submission = make_submission()
    author = submission.author.user
    author.groups.add(Group.objects.get(name=roles.REVIEWER))

    content = org_client.get(panel_url(reviewing)).content.decode()

    assert f'value="{author.pk}"' not in content


def test_assign_is_not_offered_outside_review_stage(
    org_client, conference, make_submission, reviewer
):
    make_submission()

    content = org_client.get(panel_url(conference)).content.decode()

    assert 'name="reviewer"' not in content


# --- решения -------------------------------------------------------------


def test_accept_and_reject_change_status(org_client, reviewing, make_submission):
    submission = make_submission()
    url = reverse("organizer_decide", args=[submission.pk])

    org_client.post(url, {"decision": "accept"}, **HTMX)
    submission.refresh_from_db()
    assert submission.status == Submission.Status.ACCEPTED

    org_client.post(url, {"decision": "reject"}, **HTMX)
    submission.refresh_from_db()
    assert submission.status == Submission.Status.REJECTED


def test_decision_row_hides_button_for_current_decision(org_client, reviewing, make_submission):
    submission = make_submission()

    response = org_client.post(
        reverse("organizer_decide", args=[submission.pk]), {"decision": "accept"}, **HTMX
    )

    content = response.content.decode()
    assert 'value="accept"' not in content
    assert 'value="reject"' in content


def test_unknown_decision_is_refused(org_client, reviewing, make_submission):
    submission = make_submission()

    response = org_client.post(
        reverse("organizer_decide", args=[submission.pk]), {"decision": "hack"}, **HTMX
    )

    submission.refresh_from_db()
    assert submission.status == Submission.Status.SUBMITTED
    assert "Неизвестное решение" in response.content.decode()


def test_decision_is_refused_outside_review_stage(org_client, conference, make_submission):
    submission = make_submission()

    response = org_client.post(
        reverse("organizer_decide", args=[submission.pk]), {"decision": "accept"}, **HTMX
    )

    submission.refresh_from_db()
    assert submission.status == Submission.Status.SUBMITTED
    assert "только на этапе рецензирования" in response.content.decode()


def test_accepted_talk_appears_in_public_program(org_client, client, reviewing, make_submission):
    submission = make_submission(title="Попадёт в программу")
    org_client.post(
        reverse("organizer_decide", args=[submission.pk]), {"decision": "accept"}, **HTMX
    )

    content = client.get(reverse("conference_program", args=[reviewing.slug])).content.decode()

    assert "Попадёт в программу" in content


# --- сервис decide без HTTP ---------------------------------------------


def test_service_decide_requires_permission(reviewing, make_submission, make_user):
    submission = make_submission()
    outsider = make_user("out@example.com", groups=[roles.REVIEWER])

    with pytest.raises(PermissionDenied):
        services.decide(submission, Submission.Status.ACCEPTED, by=outsider)


def test_service_decide_refuses_draft(reviewing, make_submission, organizer):
    draft = make_submission(status=Submission.Status.DRAFT)

    with pytest.raises(SubmissionError, match="Черновик"):
        services.decide(draft, Submission.Status.ACCEPTED, by=organizer)

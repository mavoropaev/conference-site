"""Этапы конференции: порядок, журнал, права, ограничения."""

import datetime

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.urls import reverse

from conferences.models import Stage, StageTransition, StageTransitionError


@pytest.fixture
def organizer(make_user):
    return make_user("org@example.com", perms=["manage_stage", "revert_stage"])


def test_new_conference_starts_at_submission(make_conference):
    conference = make_conference()

    assert conference.stage == Stage.SUBMISSION


def test_advance_walks_the_whole_chain_in_order(make_conference, organizer):
    conference = make_conference()

    visited = [conference.stage]
    for _ in range(len(Stage.values) - 1):
        conference.advance(by=organizer)
        visited.append(conference.stage)

    assert visited == Stage.values


def test_advance_persists_stage_in_database(make_conference, organizer):
    conference = make_conference()

    conference.advance(by=organizer)

    conference.refresh_from_db()
    assert conference.stage == Stage.REVIEW


def test_advance_writes_journal_entry(make_conference, organizer):
    conference = make_conference()

    transition = conference.advance(by=organizer)

    assert transition.from_stage == Stage.SUBMISSION
    assert transition.to_stage == Stage.REVIEW
    assert transition.changed_by == organizer
    assert StageTransition.objects.filter(conference=conference).count() == 1


def test_cannot_advance_past_finished(make_conference, organizer):
    conference = make_conference(stage=Stage.FINISHED)

    with pytest.raises(StageTransitionError):
        conference.advance(by=organizer)

    assert conference.stage == Stage.FINISHED
    assert not StageTransition.objects.exists()


def test_advance_without_permission_is_denied_and_changes_nothing(make_conference, make_user):
    conference = make_conference()
    outsider = make_user("outsider@example.com")

    with pytest.raises(PermissionDenied):
        conference.advance(by=outsider)

    conference.refresh_from_db()
    assert conference.stage == Stage.SUBMISSION
    assert not StageTransition.objects.exists()


def test_revert_goes_back_one_stage_and_logs_reason(make_conference, organizer):
    conference = make_conference(stage=Stage.REGISTRATION)

    transition = conference.revert(by=organizer, reason="Нужно доприслать рецензии")

    conference.refresh_from_db()
    assert conference.stage == Stage.REVIEW
    assert transition.reason == "Нужно доприслать рецензии"


def test_revert_requires_a_reason(make_conference, organizer):
    conference = make_conference(stage=Stage.REVIEW)

    with pytest.raises(StageTransitionError):
        conference.revert(by=organizer, reason="   ")

    conference.refresh_from_db()
    assert conference.stage == Stage.REVIEW


def test_revert_requires_its_own_permission(make_conference, make_user):
    # Право продвигать конференцию вперёд не даёт права возвращать её назад.
    only_advance = make_user("adv@example.com", perms=["manage_stage"])
    conference = make_conference(stage=Stage.REVIEW)

    with pytest.raises(PermissionDenied):
        conference.revert(by=only_advance, reason="ошибка")


def test_cannot_revert_from_first_stage(make_conference, organizer):
    conference = make_conference()

    with pytest.raises(StageTransitionError):
        conference.revert(by=organizer, reason="некуда")


@pytest.mark.parametrize(
    ("stage", "submissions", "reviews", "registration"),
    [
        (Stage.SUBMISSION, True, False, False),
        (Stage.REVIEW, False, True, False),
        (Stage.REGISTRATION, False, False, True),
        (Stage.ONGOING, False, False, False),
        (Stage.FINISHED, False, False, False),
    ],
)
def test_stage_controls_available_features(
    make_conference, stage, submissions, reviews, registration
):
    conference = make_conference(stage=stage)

    assert conference.accepts_submissions is submissions
    assert conference.reviews_open is reviews
    assert conference.registration_open is registration


def test_end_date_cannot_precede_start_date(make_conference):
    with pytest.raises(IntegrityError):
        make_conference(
            start_date=datetime.date(2026, 10, 5),
            end_date=datetime.date(2026, 10, 1),
        )


def test_admin_action_advances_stage(client, make_conference, make_user):
    superuser = make_user("root@example.com", is_staff=True, is_superuser=True)
    conference = make_conference()
    client.force_login(superuser)

    response = client.post(
        reverse("admin:conferences_conference_changelist"),
        {"action": "advance_stage", "_selected_action": [conference.pk]},
        follow=True,
    )

    conference.refresh_from_db()
    assert response.status_code == 200
    assert conference.stage == Stage.REVIEW

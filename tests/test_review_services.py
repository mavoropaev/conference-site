"""Правила рецензирования: кого и когда можно назначить, кто и когда может оценивать."""

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

from accounts import roles
from conferences.models import Stage
from reviews import services
from reviews.models import Review
from reviews.services import ReviewError
from submissions.models import Submission


@pytest.fixture
def organizer(make_user):
    return make_user("org@example.com", groups=[roles.ORGANIZER])


@pytest.fixture
def reviewer(make_user):
    return make_user("rev@example.com", groups=[roles.REVIEWER])


@pytest.fixture
def submission(make_conference, make_user):
    conference = make_conference(stage=Stage.REVIEW)
    return Submission.objects.create(
        conference=conference,
        author=make_user("author@example.com").profile,
        title="Доклад",
        abstract="Текст",
        status=Submission.Status.SUBMITTED,
    )


# --- назначение ---------------------------------------------------------


def test_organizer_assigns_reviewer(submission, reviewer, organizer):
    review = services.assign_reviewer(submission, reviewer, by=organizer)

    assert review.submission == submission
    assert review.reviewer == reviewer
    assert review.score is None


def test_assignment_requires_permission(submission, reviewer, make_user):
    outsider = make_user("out@example.com", groups=[roles.REVIEWER])

    with pytest.raises(PermissionDenied):
        services.assign_reviewer(submission, reviewer, by=outsider)

    assert not Review.objects.exists()


def test_assignment_only_during_review_stage(submission, reviewer, organizer):
    submission.conference.stage = Stage.SUBMISSION

    with pytest.raises(ReviewError, match="этапе рецензирования"):
        services.assign_reviewer(submission, reviewer, by=organizer)


@pytest.mark.parametrize("status", [Submission.Status.DRAFT, Submission.Status.REJECTED])
def test_assignment_only_for_submitted_submissions(submission, reviewer, organizer, status):
    submission.status = status

    with pytest.raises(ReviewError, match="поданную"):
        services.assign_reviewer(submission, reviewer, by=organizer)


def test_assignment_requires_reviewer_role(submission, organizer, make_user):
    participant = make_user("part@example.com", groups=[roles.PARTICIPANT])

    with pytest.raises(ReviewError, match="Рецензент"):
        services.assign_reviewer(submission, participant, by=organizer)


def test_author_cannot_review_own_submission(submission, organizer):
    # Автор заявки сам состоит в роли рецензента, но свою заявку рецензировать не может.
    author = submission.author.user
    author.groups.add(Group.objects.get(name=roles.REVIEWER))

    with pytest.raises(ReviewError, match="собственную"):
        services.assign_reviewer(submission, author, by=organizer)

    assert not Review.objects.exists()


def test_same_reviewer_cannot_be_assigned_twice(submission, reviewer, organizer):
    services.assign_reviewer(submission, reviewer, by=organizer)

    with pytest.raises(ReviewError, match="уже назначен"):
        services.assign_reviewer(submission, reviewer, by=organizer)

    assert Review.objects.count() == 1


# --- сохранение рецензии ------------------------------------------------


def test_save_review_stores_score_and_comment(submission, reviewer):
    review = Review.objects.create(submission=submission, reviewer=reviewer)

    services.save_review(review, score=4, comment="Хорошая работа")

    review.refresh_from_db()
    assert review.score == 4
    assert review.comment == "Хорошая работа"
    assert review.is_completed


def test_review_can_be_edited_while_review_stage_lasts(submission, reviewer):
    review = Review.objects.create(submission=submission, reviewer=reviewer, score=2)

    services.save_review(review, score=5)

    review.refresh_from_db()
    assert review.score == 5


@pytest.mark.parametrize("score", [0, 6, -1])
def test_score_outside_range_is_refused(submission, reviewer, score):
    review = Review.objects.create(submission=submission, reviewer=reviewer)

    with pytest.raises(ReviewError):
        services.save_review(review, score=score)

    review.refresh_from_db()
    assert review.score is None


@pytest.mark.parametrize("stage", [Stage.SUBMISSION, Stage.REGISTRATION, Stage.FINISHED])
def test_review_cannot_be_saved_outside_review_stage(submission, reviewer, stage):
    review = Review.objects.create(submission=submission, reviewer=reviewer)
    submission.conference.stage = stage

    with pytest.raises(ReviewError, match="закрыт"):
        services.save_review(review, score=3)

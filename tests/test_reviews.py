"""Рецензии: ограничения БД (уникальность, диапазон оценки) и поведение."""

import pytest
from django.db import IntegrityError
from django.urls import reverse

from reviews.models import Review
from submissions.models import Submission


@pytest.fixture
def submission(make_conference, make_user):
    author = make_user("author@example.com").profile
    return Submission.objects.create(
        conference=make_conference(), author=author, title="Доклад", abstract="Текст"
    )


@pytest.fixture
def reviewer(make_user):
    return make_user("reviewer@example.com")


def test_review_can_be_assigned_without_score(submission, reviewer):
    review = Review.objects.create(submission=submission, reviewer=reviewer)

    assert review.score is None
    assert not review.is_completed


def test_review_with_score_is_completed(submission, reviewer):
    review = Review.objects.create(submission=submission, reviewer=reviewer, score=4)

    assert review.is_completed


@pytest.mark.parametrize("score", [1, 3, 5])
def test_scores_from_one_to_five_are_allowed(submission, reviewer, score):
    Review.objects.create(submission=submission, reviewer=reviewer, score=score)


@pytest.mark.parametrize("score", [0, 6, 100])
def test_score_out_of_range_is_rejected_by_database(submission, reviewer, score):
    with pytest.raises(IntegrityError):
        Review.objects.create(submission=submission, reviewer=reviewer, score=score)


def test_reviewer_cannot_review_same_submission_twice(submission, reviewer):
    Review.objects.create(submission=submission, reviewer=reviewer)

    with pytest.raises(IntegrityError):
        Review.objects.create(submission=submission, reviewer=reviewer, score=3)


def test_same_reviewer_can_review_different_submissions(submission, reviewer):
    other = Submission.objects.create(
        conference=submission.conference,
        author=submission.author,
        title="Другой доклад",
        abstract="Текст",
    )

    Review.objects.create(submission=submission, reviewer=reviewer)
    Review.objects.create(submission=other, reviewer=reviewer)

    assert reviewer.reviews.count() == 2


def test_different_reviewers_can_review_same_submission(submission, make_user):
    Review.objects.create(submission=submission, reviewer=make_user("r1@example.com"))
    Review.objects.create(submission=submission, reviewer=make_user("r2@example.com"))

    assert submission.reviews.count() == 2


def test_deleting_submission_deletes_its_reviews(submission, reviewer):
    Review.objects.create(submission=submission, reviewer=reviewer)

    submission.delete()

    assert not Review.objects.exists()


def test_admin_list_renders(client, make_user, submission, reviewer):
    Review.objects.create(submission=submission, reviewer=reviewer, score=5)
    client.force_login(make_user("root@example.com", is_staff=True, is_superuser=True))

    response = client.get(reverse("admin:reviews_review_changelist"))

    assert response.status_code == 200

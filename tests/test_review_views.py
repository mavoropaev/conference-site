"""Интерфейс рецензента: доступ, слепое рецензирование, форма оценки на HTMX."""

import pytest
from django.urls import reverse

from accounts import roles
from conferences.models import Stage
from reviews.models import Review
from submissions.models import Submission

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def reviewer(make_user):
    return make_user("rev@example.com", groups=[roles.REVIEWER])


@pytest.fixture
def submission(make_conference, make_user):
    author = make_user("secret-author@example.com", first_name="Тайна", last_name="Авторова")
    return Submission.objects.create(
        conference=make_conference(stage=Stage.REVIEW),
        author=author.profile,
        title="Рецензируемый доклад",
        abstract="Аннотация доклада",
        status=Submission.Status.SUBMITTED,
    )


@pytest.fixture
def review(submission, reviewer):
    return Review.objects.create(submission=submission, reviewer=reviewer)


@pytest.fixture
def reviewer_client(client, reviewer):
    client.force_login(reviewer)
    return client


def detail_url(review):
    return reverse("review_detail", args=[review.pk])


# --- доступ ---------------------------------------------------------------


def test_anonymous_is_redirected_to_login(client, review):
    for url in (reverse("review_list"), detail_url(review)):
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("login") in response["Location"]


def test_participant_without_reviewer_role_gets_403(client, make_user, review):
    client.force_login(make_user("part@example.com", groups=[roles.PARTICIPANT]))

    assert client.get(reverse("review_list")).status_code == 403
    assert client.get(detail_url(review)).status_code == 403


def test_other_reviewers_review_returns_404(client, make_user, review):
    client.force_login(make_user("rev2@example.com", groups=[roles.REVIEWER]))

    assert client.get(detail_url(review)).status_code == 404
    assert client.post(detail_url(review), {"score": 5}).status_code == 404


def test_list_shows_only_own_reviews(reviewer_client, make_user, submission, review):
    other = make_user("rev2@example.com", groups=[roles.REVIEWER])
    another_submission = Submission.objects.create(
        conference=submission.conference,
        author=submission.author,
        title="Чужая рецензия",
        abstract="Текст",
        status=Submission.Status.SUBMITTED,
    )
    Review.objects.create(submission=another_submission, reviewer=other)

    content = reviewer_client.get(reverse("review_list")).content.decode()

    assert "Рецензируемый доклад" in content
    assert "Чужая рецензия" not in content


def test_navigation_link_only_for_reviewers(client, reviewer, make_user):
    client.force_login(reviewer)
    reviewer_page = client.get(reverse("home")).content.decode()
    client.force_login(make_user("part@example.com", groups=[roles.PARTICIPANT]))
    participant_page = client.get(reverse("home")).content.decode()

    assert "Мои рецензии" in reviewer_page
    assert "Мои рецензии" not in participant_page


# --- слепое рецензирование ------------------------------------------------


def test_reviewer_does_not_see_author(reviewer_client, review):
    for url in (reverse("review_list"), detail_url(review)):
        content = reviewer_client.get(url).content.decode()

        assert "Авторова" not in content
        assert "Тайна" not in content
        assert "secret-author" not in content


def test_reviewer_sees_submission_text(reviewer_client, review):
    content = reviewer_client.get(detail_url(review)).content.decode()

    assert "Рецензируемый доклад" in content
    assert "Аннотация доклада" in content


# --- форма оценки ---------------------------------------------------------


def test_detail_is_page_without_htmx_and_fragment_with_it(reviewer_client, review):
    assert "<html" in reviewer_client.get(detail_url(review)).content.decode()
    assert "<html" not in reviewer_client.get(detail_url(review), **HTMX).content.decode()


def test_valid_review_via_htmx_is_saved_and_confirmed(reviewer_client, review):
    response = reviewer_client.post(
        detail_url(review), {"score": "4", "comment": "Убедительно"}, **HTMX
    )

    review.refresh_from_db()
    assert review.score == 4
    assert review.comment == "Убедительно"
    assert "Рецензия сохранена" in response.content.decode()
    assert "<html" not in response.content.decode()


def test_valid_review_without_htmx_redirects(reviewer_client, review):
    response = reviewer_client.post(detail_url(review), {"score": "5"})

    review.refresh_from_db()
    assert response.status_code == 302
    assert review.score == 5


@pytest.mark.parametrize("score", ["", "0", "6", "abc"])
def test_invalid_score_is_rejected_with_form_errors(reviewer_client, review, score):
    response = reviewer_client.post(detail_url(review), {"score": score}, **HTMX)

    review.refresh_from_db()
    assert review.score is None
    assert "errorlist" in response.content.decode()


def test_existing_review_is_prefilled(reviewer_client, review):
    review.score = 3
    review.comment = "Ранее написанный комментарий"
    review.save()

    content = reviewer_client.get(detail_url(review)).content.decode()

    assert "Ранее написанный комментарий" in content
    assert 'value="3" selected' in content


def test_form_is_replaced_by_notice_after_review_stage(reviewer_client, review):
    review.submission.conference.stage = Stage.REGISTRATION
    review.submission.conference.save()

    page = reviewer_client.get(detail_url(review)).content.decode()
    response = reviewer_client.post(detail_url(review), {"score": "5"}, **HTMX)

    review.refresh_from_db()
    assert "<form" not in page.split("</header>")[1]
    assert "Этап рецензирования не идёт" in page
    assert review.score is None
    assert "Этап рецензирования не идёт" in response.content.decode()

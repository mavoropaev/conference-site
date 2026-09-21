"""Заявки автора: доступ, этапы, HTMX-фрагменты и запасной вариант без JS."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from conferences.models import Stage
from submissions import services
from submissions.models import Submission
from submissions.services import SubmissionError

HTMX = {"HTTP_HX_REQUEST": "true"}
FORM_DATA = {"title": "Новый метод", "abstract": "Описание метода."}


@pytest.fixture
def user(make_user):
    return make_user("author@example.com")


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def conference(make_conference):
    return make_conference(slug="open-conf", title="Открытая конференция")


@pytest.fixture
def submission(conference, user):
    return Submission.objects.create(
        conference=conference, author=user.profile, title="Мой доклад", abstract="Текст"
    )


def is_fragment(response):
    return "<html" not in response.content.decode()


# --- доступ ---------------------------------------------------------------


@pytest.mark.parametrize(
    "url_name, args",
    [
        ("submission_list", []),
        ("submission_create", ["open-conf"]),
        ("submission_detail", [1]),
        ("submission_edit", [1]),
    ],
)
def test_anonymous_is_redirected_to_login(client, conference, url_name, args):
    response = client.get(reverse(url_name, args=args))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]


def test_other_users_submission_returns_404(client, make_user, submission):
    client.force_login(make_user("stranger@example.com"))

    for url_name in ("submission_detail", "submission_edit"):
        assert client.get(reverse(url_name, args=[submission.pk])).status_code == 404
    assert client.post(reverse("submission_submit", args=[submission.pk])).status_code == 404


def test_list_shows_only_own_submissions(logged_client, make_user, submission, conference):
    Submission.objects.create(
        conference=conference,
        author=make_user("other@example.com").profile,
        title="Чужой доклад",
        abstract="Текст",
    )

    content = logged_client.get(reverse("submission_list")).content.decode()

    assert "Мой доклад" in content
    assert "Чужой доклад" not in content


# --- создание -------------------------------------------------------------


def test_create_form_is_full_page_without_htmx_and_fragment_with_it(logged_client, conference):
    url = reverse("submission_create", args=[conference.slug])

    assert not is_fragment(logged_client.get(url))
    assert is_fragment(logged_client.get(url, **HTMX))


def test_create_without_htmx_redirects_and_saves_draft_for_current_author(
    logged_client, user, conference
):
    response = logged_client.post(reverse("submission_create", args=[conference.slug]), FORM_DATA)

    submission = Submission.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("submission_detail", args=[submission.pk])
    assert submission.author == user.profile
    assert submission.conference == conference
    assert submission.status == Submission.Status.DRAFT


def test_create_with_htmx_returns_card_and_pushes_url(logged_client, conference):
    response = logged_client.post(
        reverse("submission_create", args=[conference.slug]), FORM_DATA, **HTMX
    )

    submission = Submission.objects.get()
    assert response.status_code == 200
    assert is_fragment(response)
    assert "Новый метод" in response.content.decode()
    assert response["HX-Push-Url"] == reverse("submission_detail", args=[submission.pk])


def test_create_with_invalid_data_rerenders_form_with_errors(logged_client, conference):
    response = logged_client.post(
        reverse("submission_create", args=[conference.slug]), {"title": "", "abstract": ""}, **HTMX
    )

    assert response.status_code == 200
    assert is_fragment(response)
    assert "errorlist" in response.content.decode()
    assert not Submission.objects.exists()


def test_create_uploads_file(logged_client, conference, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    data = {**FORM_DATA, "file": SimpleUploadedFile("paper.pdf", b"%PDF-1.4 test")}

    logged_client.post(reverse("submission_create", args=[conference.slug]), data)

    assert Submission.objects.get().file.name == "submissions/open-conf/paper.pdf"


def test_create_rejects_disallowed_file_type(logged_client, conference, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    data = {**FORM_DATA, "file": SimpleUploadedFile("run.exe", b"binary")}

    logged_client.post(reverse("submission_create", args=[conference.slug]), data)

    assert not Submission.objects.exists()


@pytest.mark.parametrize("stage", [Stage.REVIEW, Stage.REGISTRATION, Stage.ONGOING, Stage.FINISHED])
def test_create_is_closed_after_submission_stage(logged_client, make_conference, stage):
    closed = make_conference(slug="closed", stage=stage)
    url = reverse("submission_create", args=[closed.slug])

    response = logged_client.post(url, FORM_DATA)

    assert response.status_code == 302
    assert response["Location"] == reverse("conference_detail", args=[closed.slug])
    assert not Submission.objects.exists()


def test_create_closed_with_htmx_uses_client_redirect(logged_client, make_conference):
    closed = make_conference(slug="closed", stage=Stage.REVIEW)

    response = logged_client.post(
        reverse("submission_create", args=[closed.slug]), FORM_DATA, **HTMX
    )

    assert response["HX-Redirect"] == reverse("conference_detail", args=[closed.slug])


# --- редактирование -------------------------------------------------------


def test_edit_form_is_prefilled_fragment_for_htmx(logged_client, submission):
    response = logged_client.get(reverse("submission_edit", args=[submission.pk]), **HTMX)

    assert is_fragment(response)
    assert "Мой доклад" in response.content.decode()


def test_edit_with_htmx_updates_and_returns_card(logged_client, submission):
    response = logged_client.post(
        reverse("submission_edit", args=[submission.pk]),
        {"title": "Уточнённое название", "abstract": "Текст"},
        **HTMX,
    )

    submission.refresh_from_db()
    assert submission.title == "Уточнённое название"
    assert "Уточнённое название" in response.content.decode()
    assert is_fragment(response)


def test_edit_is_refused_after_stage_moves_on(logged_client, submission):
    submission.conference.stage = Stage.REVIEW
    submission.conference.save()

    response = logged_client.post(
        reverse("submission_edit", args=[submission.pk]),
        {"title": "Взлом", "abstract": "Текст"},
        **HTMX,
    )

    submission.refresh_from_db()
    assert submission.title == "Мой доклад"
    assert "закрыт" in response.content.decode()


def test_accepted_submission_cannot_be_edited(logged_client, submission):
    submission.status = Submission.Status.ACCEPTED
    submission.save()

    logged_client.post(
        reverse("submission_edit", args=[submission.pk]),
        {"title": "Взлом", "abstract": "Текст"},
    )

    submission.refresh_from_db()
    assert submission.title == "Мой доклад"


# --- отправка -------------------------------------------------------------


def test_submit_moves_draft_to_submitted(logged_client, submission):
    response = logged_client.post(reverse("submission_submit", args=[submission.pk]), **HTMX)

    submission.refresh_from_db()
    assert submission.status == Submission.Status.SUBMITTED
    assert "Отправить на рассмотрение" not in response.content.decode()


def test_submit_requires_post(logged_client, submission):
    response = logged_client.get(reverse("submission_submit", args=[submission.pk]))

    assert response.status_code == 405


def test_submit_twice_is_refused_with_message(logged_client, submission):
    url = reverse("submission_submit", args=[submission.pk])
    logged_client.post(url, **HTMX)

    response = logged_client.post(url, **HTMX)

    assert "уже отправлена" in response.content.decode()


def test_submit_is_refused_when_stage_closed(logged_client, submission):
    submission.conference.stage = Stage.REVIEW
    submission.conference.save()

    logged_client.post(reverse("submission_submit", args=[submission.pk]), **HTMX)

    submission.refresh_from_db()
    assert submission.status == Submission.Status.DRAFT


def test_edit_and_submit_buttons_depend_on_state(logged_client, submission):
    url = reverse("submission_detail", args=[submission.pk])

    draft = logged_client.get(url).content.decode()
    submission.status = Submission.Status.SUBMITTED
    submission.save()
    sent = logged_client.get(url).content.decode()

    assert "Редактировать" in draft and "Отправить на рассмотрение" in draft
    assert "Редактировать" in sent and "Отправить на рассмотрение" not in sent


# --- сервисный слой без HTTP ---------------------------------------------


def test_service_can_edit_reflects_stage_and_status(submission):
    assert services.can_edit(submission)

    submission.status = Submission.Status.REJECTED
    assert not services.can_edit(submission)


def test_service_submit_raises_when_stage_closed(submission):
    submission.conference.stage = Stage.FINISHED

    with pytest.raises(SubmissionError):
        services.submit(submission)


# --- вход на страницу конференции -----------------------------------------


def test_conference_page_offers_submission_only_while_open(client, make_conference, user):
    open_conf = make_conference(slug="open")
    closed = make_conference(slug="closed", stage=Stage.REVIEW)
    client.force_login(user)

    open_page = client.get(reverse("conference_detail", args=[open_conf.slug])).content.decode()
    closed_page = client.get(reverse("conference_detail", args=[closed.slug])).content.decode()

    assert "Подать заявку" in open_page
    assert "Подать заявку" not in closed_page

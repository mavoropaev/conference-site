"""Каркас интерфейса: публичные страницы, регистрация, вход и выход."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts import roles

SIGNUP_DATA = {
    "email": "new@example.com",
    "first_name": "Иван",
    "last_name": "Петров",
    "password1": "long-enough-pass-42",
    "password2": "long-enough-pass-42",
}


def test_home_lists_conferences(client, make_conference):
    make_conference(title="Конференция по физике", slug="physics")

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert "Конференция по физике" in response.content.decode()


def test_home_without_conferences_shows_placeholder(client, db):
    response = client.get(reverse("home"))

    assert "Пока нет ни одной конференции" in response.content.decode()


def test_conference_detail_shows_title_and_stage(client, make_conference):
    make_conference(title="Конференция по химии", slug="chem", stage="review")

    response = client.get(reverse("conference_detail", args=["chem"]))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Конференция по химии" in content
    assert "Рецензирование" in content


def test_unknown_conference_returns_404(client, db):
    response = client.get(reverse("conference_detail", args=["nope"]))

    assert response.status_code == 404


def test_base_template_loads_local_htmx_with_csrf_header(client, db):
    content = client.get(reverse("home")).content.decode()

    assert "vendor/htmx.min.js" in content
    assert "X-CSRFToken" in content


def test_signup_creates_user_participant_role_and_logs_in(client, db):
    response = client.post(reverse("signup"), SIGNUP_DATA)

    user = get_user_model().objects.get(email="new@example.com")
    assert response.status_code == 302
    assert user.groups.filter(name=roles.PARTICIPANT).exists()
    assert user.profile.pk
    assert client.session["_auth_user_id"] == str(user.pk)


def test_signup_rejects_email_differing_only_in_case(client, make_user):
    make_user("New@Example.com")

    response = client.post(reverse("signup"), SIGNUP_DATA)

    assert response.status_code == 200
    assert "уже зарегистрирован" in response.content.decode()
    assert get_user_model().objects.count() == 1


def test_signup_rejects_mismatched_passwords(client, db):
    response = client.post(reverse("signup"), {**SIGNUP_DATA, "password2": "different-pass-42"})

    assert response.status_code == 200
    assert not get_user_model().objects.exists()


def test_login_with_email_and_password(client, make_user):
    make_user("me@example.com")

    response = client.post(
        reverse("login"), {"username": "me@example.com", "password": "pass-12345-test"}
    )

    assert response.status_code == 302
    assert "_auth_user_id" in client.session


def test_login_with_wrong_password_fails(client, make_user):
    make_user("me@example.com")

    response = client.post(
        reverse("login"), {"username": "me@example.com", "password": "wrong-pass"}
    )

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_logout_requires_post_and_ends_session(client, make_user):
    client.force_login(make_user("me@example.com"))

    assert client.get(reverse("logout")).status_code == 405
    response = client.post(reverse("logout"))

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_header_shows_login_links_for_anonymous_and_email_for_user(client, make_user):
    anonymous = client.get(reverse("home")).content.decode()
    client.force_login(make_user("me@example.com"))
    authenticated = client.get(reverse("home")).content.decode()

    assert "Войти" in anonymous and "Регистрация" in anonymous
    assert "me@example.com" in authenticated and "Выйти" in authenticated

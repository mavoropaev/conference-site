"""Дымовые тесты: проект собирается, главная открывается, пользователь создаётся по email."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_home_page_renders(client):
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert "Научная конференция" in response.content.decode()


@pytest.mark.django_db
def test_user_is_created_with_email_and_normalized():
    user_model = get_user_model()

    user = user_model.objects.create_user(email="Ivan@Example.COM", password="s3cret-pass")

    assert user.email == "Ivan@example.com"
    assert user.check_password("s3cret-pass")
    assert not user.is_staff


@pytest.mark.django_db
def test_create_user_without_email_fails():
    user_model = get_user_model()

    with pytest.raises(ValueError):
        user_model.objects.create_user(email="", password="s3cret-pass")


@pytest.mark.django_db
def test_superuser_has_staff_flags():
    user_model = get_user_model()

    admin = user_model.objects.create_superuser(email="admin@example.com", password="s3cret-pass")

    assert admin.is_staff
    assert admin.is_superuser

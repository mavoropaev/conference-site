import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from conferences.models import Conference


@pytest.fixture
def make_user(db):
    """Фабрика пользователей: `make_user("a@example.com", perms=["manage_stage"])`."""

    def _make(email="user@example.com", perms=(), **extra):
        user = get_user_model().objects.create_user(
            email=email, password="pass-12345-test", **extra
        )
        for codename in perms:
            user.user_permissions.add(Permission.objects.get(codename=codename))
        return user

    return _make


@pytest.fixture
def make_conference(db):
    """Фабрика конференций с разумными значениями по умолчанию."""

    def _make(**overrides):
        fields = {
            "title": "Конференция 2026",
            "slug": "conf-2026",
            "start_date": datetime.date(2026, 10, 1),
            "end_date": datetime.date(2026, 10, 3),
        }
        fields.update(overrides)
        return Conference.objects.create(**fields)

    return _make

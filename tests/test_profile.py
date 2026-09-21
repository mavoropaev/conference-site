"""Профиль участника: автосоздание, валидация ORCID, идентификатор старой системы."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from accounts.models import Profile, validate_orcid

# Тестовый ORCID из документации ORCID (вымышленный исследователь Josiah Carberry).
VALID_ORCID = "0000-0002-1825-0097"


def test_profile_is_created_together_with_user(make_user):
    user = make_user("new@example.com")

    assert Profile.objects.filter(user=user).exists()
    assert user.profile.affiliation == ""


def test_profile_is_deleted_with_user(make_user):
    user = make_user("gone@example.com")

    user.delete()

    assert not Profile.objects.exists()


def test_valid_orcid_is_accepted():
    validate_orcid(VALID_ORCID)


def test_orcid_with_x_check_digit_is_accepted():
    # Контрольная цифра 10 записывается как X.
    validate_orcid("0000-0002-1694-233X")


@pytest.mark.parametrize(
    "value",
    ["", "1234", "0000-0002-1825-009", "0000000218250097", "abcd-0002-1825-0097"],
)
def test_orcid_with_wrong_format_is_rejected(value):
    with pytest.raises(ValidationError):
        validate_orcid(value)


def test_orcid_with_wrong_check_digit_is_rejected():
    with pytest.raises(ValidationError, match="контрольная цифра"):
        validate_orcid("0000-0002-1825-0098")


def test_blank_orcid_is_allowed_in_full_clean(make_user):
    profile = make_user("blank@example.com").profile

    profile.full_clean()


def test_legacy_id_must_be_unique(make_user):
    first = make_user("a@example.com").profile
    second = make_user("b@example.com").profile
    first.legacy_id = "drupal-42"
    first.save()

    second.legacy_id = "drupal-42"
    with pytest.raises(IntegrityError):
        second.save()


def test_many_profiles_without_legacy_id_do_not_conflict(make_user):
    make_user("a@example.com")
    make_user("b@example.com")

    assert Profile.objects.filter(legacy_id__isnull=True).count() == 2


def test_user_admin_change_page_shows_profile(client, make_user):
    superuser = make_user("root@example.com", is_staff=True, is_superuser=True)
    client.force_login(superuser)

    response = client.get(reverse("admin:accounts_user_change", args=[superuser.pk]))

    assert response.status_code == 200
    assert "ORCID" in response.content.decode()

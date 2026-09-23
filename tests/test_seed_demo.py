"""Команда seed_demo: повторный запуск не плодит дубли, данные пригодны для работы."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from accounts import roles
from conferences.models import Conference, Stage
from submissions import selectors
from submissions.models import Submission

pytestmark = pytest.mark.django_db


def counts():
    return (
        get_user_model().objects.count(),
        Conference.objects.count(),
        Submission.objects.count(),
    )


def test_seed_is_idempotent():
    call_command("seed_demo", verbosity=0)
    first = counts()

    call_command("seed_demo", verbosity=0)

    assert counts() == first


def test_seed_creates_conferences_at_three_stages():
    call_command("seed_demo", verbosity=0)

    stages = set(Conference.objects.values_list("stage", flat=True))

    assert stages == {Stage.SUBMISSION, Stage.REVIEW, Stage.FINISHED}


def test_seed_users_can_log_in_and_have_roles(client):
    call_command("seed_demo", verbosity=0)

    organizer = get_user_model().objects.get(email="organizer@example.com")

    assert client.login(username="organizer@example.com", password="demo-pass-123")
    assert organizer.groups.filter(name=roles.ORGANIZER).exists()
    assert organizer.has_perm("conferences.manage_stage")


def test_archive_program_has_more_than_one_page_and_several_countries():
    call_command("seed_demo", verbosity=0)
    archive = Conference.objects.get(slug="conf-2025")

    assert selectors.accepted_submissions(archive).count() > 10
    assert len(selectors.program_countries(archive)) > 1

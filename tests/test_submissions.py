"""Заявки на доклады и регистрации: значения по умолчанию, файлы, ограничения БД."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.urls import reverse

from submissions.models import MAX_FILE_SIZE_MB, Registration, Submission


@pytest.fixture
def author(make_user):
    return make_user("author@example.com").profile


@pytest.fixture
def conference(make_conference):
    return make_conference()


def make_submission(conference, author, **overrides):
    fields = {"conference": conference, "author": author, "title": "Доклад", "abstract": "Текст"}
    fields.update(overrides)
    return Submission.objects.create(**fields)


def test_new_submission_is_a_draft(conference, author):
    submission = make_submission(conference, author)

    assert submission.status == Submission.Status.DRAFT


def test_file_is_optional(conference, author):
    submission = make_submission(conference, author)

    submission.full_clean()


def test_file_with_disallowed_extension_is_rejected(conference, author):
    submission = make_submission(conference, author)
    submission.file = SimpleUploadedFile("virus.exe", b"data")

    with pytest.raises(ValidationError) as error:
        submission.full_clean()

    assert "file" in error.value.message_dict


def test_pdf_file_is_accepted(conference, author):
    submission = make_submission(conference, author)
    submission.file = SimpleUploadedFile("paper.pdf", b"%PDF-1.4 test")

    submission.full_clean()


def test_too_large_file_is_rejected(conference, author):
    submission = make_submission(conference, author)
    big = SimpleUploadedFile("paper.pdf", b"0" * (MAX_FILE_SIZE_MB * 1024 * 1024 + 1))
    submission.file = big

    with pytest.raises(ValidationError) as error:
        submission.full_clean()

    assert "file" in error.value.message_dict


def test_file_is_stored_under_conference_slug(conference, author, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    submission = make_submission(conference, author)

    submission.file.save("paper.pdf", SimpleUploadedFile("paper.pdf", b"%PDF-1.4 test"))

    assert submission.file.name.startswith(f"submissions/{conference.slug}/")


def test_deleting_conference_deletes_its_submissions(conference, author):
    make_submission(conference, author)

    conference.delete()

    assert not Submission.objects.exists()


def test_participant_can_register_once_per_conference(conference, author):
    Registration.objects.create(conference=conference, participant=author)

    with pytest.raises(IntegrityError):
        Registration.objects.create(conference=conference, participant=author)


def test_participant_can_register_for_different_conferences(make_conference, author):
    first = make_conference(slug="conf-a")
    second = make_conference(slug="conf-b")

    Registration.objects.create(conference=first, participant=author)
    Registration.objects.create(conference=second, participant=author)

    assert author.registrations.count() == 2


def test_admin_lists_render(client, make_user, conference, author):
    make_submission(conference, author)
    Registration.objects.create(conference=conference, participant=author)
    client.force_login(make_user("root@example.com", is_staff=True, is_superuser=True))

    for name in ("submission", "registration"):
        response = client.get(reverse(f"admin:submissions_{name}_changelist"))
        assert response.status_code == 200

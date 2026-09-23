"""Команда import_legacy: чтение CSV, --dry-run, устойчивость к ошибкам и CSV-пример репозитория."""

import csv
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from conferences.models import Conference
from submissions.models import Registration, Submission

pytestmark = pytest.mark.django_db

USERS_HEADER = ["legacy_id", "email", "first_name", "last_name", "affiliation", "country", "orcid"]
PARTICIPATIONS_HEADER = [
    "legacy_id",
    "conference_slug",
    "conference_title",
    "conference_start_date",
    "conference_end_date",
    "conference_location",
    "role",
    "submission_title",
    "submission_abstract",
    "status",
]


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


@pytest.fixture
def csv_files(tmp_path):
    users = write_csv(
        tmp_path / "users.csv",
        USERS_HEADER,
        [
            {
                "legacy_id": "drupal-1",
                "email": "cmd.user@example.com",
                "first_name": "Тест",
                "last_name": "Командный",
                "affiliation": "",
                "country": "",
                "orcid": "",
            }
        ],
    )
    participations = write_csv(
        tmp_path / "participations.csv",
        PARTICIPATIONS_HEADER,
        [
            {
                "legacy_id": "drupal-1",
                "conference_slug": "cmd-conf",
                "conference_title": "Командная конференция",
                "conference_start_date": "2020-01-10",
                "conference_end_date": "2020-01-12",
                "conference_location": "Тестгород",
                "role": "author",
                "submission_title": "Командный доклад",
                "submission_abstract": "Текст",
                "status": "accepted",
            }
        ],
    )
    return users, participations


def test_command_imports_users_and_participations(csv_files):
    users_csv, participations_csv = csv_files

    call_command("import_legacy", users_csv, participations_csv)

    assert get_user_model().objects.filter(email="cmd.user@example.com").exists()
    assert Conference.objects.filter(slug="cmd-conf").exists()
    assert Submission.objects.filter(title="Командный доклад").exists()


def test_command_prints_report(csv_files):
    users_csv, participations_csv = csv_files
    out = io.StringIO()

    call_command("import_legacy", users_csv, participations_csv, stdout=out)

    output = out.getvalue()
    assert "Пользователи: создано 1" in output
    assert "Доклады: создано 1" in output


def test_dry_run_reports_but_does_not_persist(csv_files):
    users_csv, participations_csv = csv_files
    out = io.StringIO()

    call_command("import_legacy", users_csv, participations_csv, "--dry-run", stdout=out)

    assert "Пробный запуск" in out.getvalue()
    assert "создано 1" in out.getvalue()
    assert not get_user_model().objects.exists()
    assert not Conference.objects.exists()


def test_command_run_twice_does_not_duplicate(csv_files):
    users_csv, participations_csv = csv_files

    call_command("import_legacy", users_csv, participations_csv)
    call_command("import_legacy", users_csv, participations_csv)

    assert get_user_model().objects.count() == 1
    assert Submission.objects.count() == 1


def test_missing_file_raises_command_error(tmp_path):
    missing = str(tmp_path / "nope.csv")

    with pytest.raises(CommandError):
        call_command("import_legacy", missing, missing)


def test_bad_row_in_middle_does_not_abort_whole_file(csv_files, tmp_path):
    _, participations_csv = csv_files
    broken = write_csv(
        tmp_path / "users_broken.csv",
        USERS_HEADER,
        [
            {
                "legacy_id": "",
                "email": "no-legacy-id@example.com",
                "first_name": "",
                "last_name": "",
                "affiliation": "",
                "country": "",
                "orcid": "",
            },
            {
                "legacy_id": "drupal-2",
                "email": "ok@example.com",
                "first_name": "",
                "last_name": "",
                "affiliation": "",
                "country": "",
                "orcid": "",
            },
        ],
    )

    call_command("import_legacy", broken, participations_csv)

    assert get_user_model().objects.filter(email="ok@example.com").exists()
    assert not get_user_model().objects.filter(email="no-legacy-id@example.com").exists()


# --- CSV-пример из репозитория ----------------------------------------------


def test_repository_example_csv_imports_cleanly():
    out = io.StringIO()

    call_command(
        "import_legacy", "legacy_data/users.csv", "legacy_data/participations.csv", stdout=out
    )

    assert get_user_model().objects.count() == 5
    assert Conference.objects.count() == 2
    assert Submission.objects.count() == 3
    assert Registration.objects.count() == 3
    assert "пропущено 0" in out.getvalue()
    assert out.getvalue().count("пропущено 0") == 4  # ни одна строка ни в одном из 4 отчётов


def test_repository_example_csv_is_idempotent():
    call_command("import_legacy", "legacy_data/users.csv", "legacy_data/participations.csv")

    call_command("import_legacy", "legacy_data/users.csv", "legacy_data/participations.csv")

    assert get_user_model().objects.count() == 5
    assert Submission.objects.count() == 3
    assert Registration.objects.count() == 3

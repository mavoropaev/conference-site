"""Перенос данных: идемпотентность, связывание по legacy_id, устойчивость к плохим строкам."""

import pytest
from django.contrib.auth import get_user_model

from accounts.models import Profile
from conferences.models import Conference, Stage
from legacy_import.services import import_participations, import_users
from submissions.models import Registration, Submission

pytestmark = pytest.mark.django_db

USER_ROW = {
    "legacy_id": "drupal-1",
    "email": "old.user@example.com",
    "first_name": "Иван",
    "last_name": "Иванов",
    "affiliation": "Институт",
    "country": "Россия",
    "orcid": "",
}

CONFERENCE_FIELDS = {
    "conference_slug": "legacy-conf",
    "conference_title": "Историческая конференция",
    "conference_start_date": "2019-05-01",
    "conference_end_date": "2019-05-03",
    "conference_location": "Старый Город",
}


# --- import_users ----------------------------------------------------------


def test_creates_new_user_with_unusable_password_and_legacy_id():
    report = import_users([USER_ROW])

    user = get_user_model().objects.get(email="old.user@example.com")
    assert report.created == 1 and report.updated == 0
    assert user.profile.legacy_id == "drupal-1"
    assert not user.has_usable_password()
    assert user.first_name == "Иван"


def test_second_run_on_same_row_is_unchanged_not_duplicated():
    import_users([USER_ROW])

    report = import_users([USER_ROW])

    assert get_user_model().objects.count() == 1
    assert report.created == 0 and report.updated == 0 and report.unchanged == 1


def test_changed_field_is_reported_as_updated_not_duplicated():
    import_users([USER_ROW])
    changed_row = {**USER_ROW, "affiliation": "Новый институт"}

    report = import_users([changed_row])

    assert get_user_model().objects.count() == 1
    assert report.updated == 1
    assert Profile.objects.get(legacy_id="drupal-1").affiliation == "Новый институт"


def test_existing_account_is_linked_by_email_instead_of_duplicated(make_user):
    existing = make_user("old.user@example.com")

    report = import_users([USER_ROW])

    assert get_user_model().objects.count() == 1
    assert report.created == 0 and report.updated == 1
    existing.refresh_from_db()
    assert existing.profile.legacy_id == "drupal-1"


@pytest.mark.parametrize(
    "row, expected_reason",
    [
        ({**USER_ROW, "legacy_id": ""}, "legacy_id"),
        ({**USER_ROW, "email": ""}, "email"),
        ({**USER_ROW, "email": "not-an-email"}, "email"),
        ({**USER_ROW, "orcid": "0000-0000-0000-0000"}, "ORCID"),
    ],
)
def test_bad_rows_are_skipped_with_reason_and_nothing_is_created(row, expected_reason):
    report = import_users([row])

    assert not get_user_model().objects.exists()
    assert len(report.skipped) == 1
    assert expected_reason.lower() in report.skipped[0].lower()


def test_valid_orcid_is_stored():
    report = import_users([{**USER_ROW, "orcid": "0000-0002-1825-0097"}])

    assert report.created == 1
    assert Profile.objects.get(legacy_id="drupal-1").orcid == "0000-0002-1825-0097"


def test_one_bad_row_does_not_break_the_rest():
    rows = [
        {**USER_ROW, "legacy_id": ""},
        {**USER_ROW, "legacy_id": "drupal-2", "email": "b@example.com"},
    ]

    report = import_users(rows)

    assert report.created == 1
    assert len(report.skipped) == 1
    assert get_user_model().objects.count() == 1


# --- import_participations: конференции -------------------------------------


def test_creates_missing_conference_as_finished():
    rows = [{**CONFERENCE_FIELDS, "legacy_id": "drupal-1", "role": "participant"}]
    import_users([USER_ROW])

    conferences_report, _, _ = import_participations(rows)

    conference = Conference.objects.get(slug="legacy-conf")
    assert conferences_report.created == 1
    assert conference.stage == Stage.FINISHED


def test_existing_conference_is_reused_and_not_recreated(make_conference):
    make_conference(slug="legacy-conf", title="Уже существует")
    import_users([USER_ROW])
    rows = [{**CONFERENCE_FIELDS, "legacy_id": "drupal-1", "role": "participant"}]

    conferences_report, _, _ = import_participations(rows)

    assert conferences_report.created == 0
    assert Conference.objects.filter(slug="legacy-conf").count() == 1
    assert Conference.objects.get(slug="legacy-conf").title == "Уже существует"


def test_unknown_conference_without_enough_data_is_skipped():
    import_users([USER_ROW])
    row = {"legacy_id": "drupal-1", "conference_slug": "no-data-conf", "role": "participant"}

    _, _, registrations_report = import_participations([row])

    assert not Conference.objects.exists()
    assert len(registrations_report.skipped) == 1


def test_invalid_conference_date_is_skipped():
    import_users([USER_ROW])
    row = {
        **CONFERENCE_FIELDS,
        "conference_start_date": "not-a-date",
        "legacy_id": "drupal-1",
        "role": "participant",
    }

    _, _, registrations_report = import_participations([row])

    assert not Conference.objects.exists()
    assert "дата" in registrations_report.skipped[0].lower()


# --- import_participations: участник должен уже существовать ---------------


def test_unknown_participant_is_skipped():
    row = {**CONFERENCE_FIELDS, "legacy_id": "no-such-id", "role": "participant"}

    _, _, registrations_report = import_participations([row])

    assert not Registration.objects.exists()
    assert "неизвестн" in registrations_report.skipped[0].lower()


def test_unknown_role_is_skipped():
    import_users([USER_ROW])
    row = {**CONFERENCE_FIELDS, "legacy_id": "drupal-1", "role": "sponsor"}

    _, _, registrations_report = import_participations([row])

    assert not Registration.objects.exists()
    assert not Submission.objects.exists()
    assert len(registrations_report.skipped) == 1


# --- роль participant: регистрация ------------------------------------------


def test_participant_role_creates_registration():
    import_users([USER_ROW])
    row = {**CONFERENCE_FIELDS, "legacy_id": "drupal-1", "role": "participant"}

    _, _, registrations_report = import_participations([row])

    assert Registration.objects.count() == 1
    assert registrations_report.created == 1


def test_second_run_does_not_duplicate_registration():
    import_users([USER_ROW])
    row = {**CONFERENCE_FIELDS, "legacy_id": "drupal-1", "role": "participant"}
    import_participations([row])

    _, _, registrations_report = import_participations([row])

    assert Registration.objects.count() == 1
    assert registrations_report.unchanged == 1


# --- роль author: заявка -----------------------------------------------------


def test_author_role_creates_accepted_submission_by_default():
    import_users([USER_ROW])
    row = {
        **CONFERENCE_FIELDS,
        "legacy_id": "drupal-1",
        "role": "author",
        "submission_title": "Исторический доклад",
        "submission_abstract": "Текст доклада.",
        "status": "",
    }

    _, submissions_report, _ = import_participations([row])

    submission = Submission.objects.get()
    assert submissions_report.created == 1
    assert submission.status == Submission.Status.ACCEPTED
    assert submission.title == "Исторический доклад"


def test_author_role_without_title_is_skipped():
    import_users([USER_ROW])
    row = {**CONFERENCE_FIELDS, "legacy_id": "drupal-1", "role": "author", "submission_title": ""}

    _, submissions_report, _ = import_participations([row])

    assert not Submission.objects.exists()
    assert len(submissions_report.skipped) == 1


def test_author_role_with_unknown_status_is_skipped():
    import_users([USER_ROW])
    row = {
        **CONFERENCE_FIELDS,
        "legacy_id": "drupal-1",
        "role": "author",
        "submission_title": "Доклад",
        "status": "published",
    }

    _, submissions_report, _ = import_participations([row])

    assert not Submission.objects.exists()
    assert len(submissions_report.skipped) == 1


def test_rerun_with_changed_status_updates_submission_without_duplicating():
    import_users([USER_ROW])
    row = {
        **CONFERENCE_FIELDS,
        "legacy_id": "drupal-1",
        "role": "author",
        "submission_title": "Доклад",
        "submission_abstract": "Текст",
        "status": "submitted",
    }
    import_participations([row])

    _, submissions_report, _ = import_participations([{**row, "status": "accepted"}])

    assert Submission.objects.count() == 1
    assert submissions_report.updated == 1
    assert Submission.objects.get().status == Submission.Status.ACCEPTED


def test_same_person_can_have_history_in_several_conferences():
    import_users([USER_ROW])
    first = {
        **CONFERENCE_FIELDS,
        "legacy_id": "drupal-1",
        "role": "author",
        "submission_title": "Доклад А",
    }
    second = {
        **CONFERENCE_FIELDS,
        "conference_slug": "legacy-conf-2",
        "legacy_id": "drupal-1",
        "role": "author",
        "submission_title": "Доклад Б",
    }

    import_participations([first, second])

    assert Submission.objects.filter(author__legacy_id="drupal-1").count() == 2
    assert Conference.objects.count() == 2


def test_full_import_is_idempotent_end_to_end():
    users = [USER_ROW]
    participations = [
        {
            **CONFERENCE_FIELDS,
            "legacy_id": "drupal-1",
            "role": "author",
            "submission_title": "Доклад",
        },
    ]

    import_users(users)
    import_participations(participations)
    counts_first_run = (
        get_user_model().objects.count(),
        Conference.objects.count(),
        Submission.objects.count(),
        Registration.objects.count(),
    )

    import_users(users)
    import_participations(participations)
    counts_second_run = (
        get_user_model().objects.count(),
        Conference.objects.count(),
        Submission.objects.count(),
        Registration.objects.count(),
    )

    assert counts_first_run == counts_second_run == (1, 1, 1, 0)

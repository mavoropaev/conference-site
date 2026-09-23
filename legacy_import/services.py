"""Перенос участников и истории участий из CSV старой системы (Drupal).

Идемпотентно: естественный ключ пользователя — `Profile.legacy_id`. Повторный запуск на тех же
файлах находит уже созданные записи по этому ключу и обновляет их, а не плодит дубли.
Каждая строка обрабатывается в своей точке сохранения (savepoint): ошибка в одной строке не
портит транзакцию для остальных — Postgres иначе потребовал бы отката всей транзакции целиком.
"""

import datetime
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from accounts.models import Profile, validate_orcid
from conferences.models import Conference, Stage
from submissions.models import Registration, Submission

DATE_FORMAT = "%Y-%m-%d"
ROLE_AUTHOR = "author"
ROLE_PARTICIPANT = "participant"
VALID_ROLES = (ROLE_AUTHOR, ROLE_PARTICIPANT)


@dataclass
class ImportReport:
    """Отчёт об импорте одной сущности: что создано, обновлено, оставлено как есть, пропущено."""

    label: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: list = field(default_factory=list)

    def skip(self, line, reason):
        self.skipped.append(f"строка {line}: {reason}")

    def __str__(self):
        text = (
            f"{self.label}: создано {self.created}, обновлено {self.updated}, "
            f"без изменений {self.unchanged}, пропущено {len(self.skipped)}"
        )
        for note in self.skipped:
            text += f"\n  - {note}"
        return text


def _clean(value):
    return (value or "").strip()


def import_users(rows):
    """Создаёт или обновляет пользователей и их профили по `legacy_id`.

    Пользователь сначала ищется по `legacy_id`; если не найден — по email (без учёта регистра),
    чтобы не плодить дубль уже зарегистрировавшемуся самостоятельно человеку, а привязать ему
    историю. Новым пользователям ставится непригодный для входа пароль: самостоятельно войти они
    не смогут, пока администратор не выдаст пароль вручную через админку — формы «забыли пароль»
    в проекте нет (см. docs/roadmap.md).
    """
    User = get_user_model()
    report = ImportReport("Пользователи")

    for line, row in enumerate(rows, start=2):
        legacy_id = _clean(row.get("legacy_id"))
        email = _clean(row.get("email"))

        if not legacy_id:
            report.skip(line, "не указан legacy_id")
            continue
        if not email:
            report.skip(line, "не указан email")
            continue
        try:
            validate_email(email)
        except ValidationError:
            report.skip(line, f"некорректный email: {email}")
            continue

        orcid = _clean(row.get("orcid"))
        if orcid:
            try:
                validate_orcid(orcid)
            except ValidationError:
                report.skip(line, f"некорректный ORCID у {email}, пропущена вся строка: {orcid}")
                continue

        user_fields = {
            "first_name": _clean(row.get("first_name")),
            "last_name": _clean(row.get("last_name")),
        }
        profile_fields = {
            "affiliation": _clean(row.get("affiliation")),
            "country": _clean(row.get("country")),
            "orcid": orcid,
        }

        try:
            with transaction.atomic():
                profile = Profile.objects.select_related("user").filter(legacy_id=legacy_id).first()
                linked = False
                if profile is None:
                    user = User.objects.filter(email__iexact=email).first()
                    if user is None:
                        user = User(email=email)
                        user.set_unusable_password()
                        user.save()
                        created = True
                    else:
                        created = False
                    profile = user.profile
                    linked = profile.legacy_id != legacy_id
                    profile.legacy_id = legacy_id
                else:
                    user = profile.user
                    created = False

                changed = (
                    created
                    or linked
                    or any(getattr(user, name) != value for name, value in user_fields.items())
                    or any(
                        getattr(profile, name) != value for name, value in profile_fields.items()
                    )
                )
                for name, value in user_fields.items():
                    setattr(user, name, value)
                user.save(update_fields=list(user_fields))
                for name, value in profile_fields.items():
                    setattr(profile, name, value)
                profile.save()
        except IntegrityError as exc:
            report.skip(line, f"{email}: конфликт данных ({exc})")
            continue

        if created:
            report.created += 1
        elif changed:
            report.updated += 1
        else:
            report.unchanged += 1

    return report


def _get_or_create_conference(row, line, report):
    slug = _clean(row.get("conference_slug"))
    if not slug:
        return None, "не указан conference_slug"

    conference = Conference.objects.filter(slug=slug).first()
    if conference is not None:
        return conference, None

    title = _clean(row.get("conference_title"))
    location = _clean(row.get("conference_location"))
    start_raw = _clean(row.get("conference_start_date"))
    end_raw = _clean(row.get("conference_end_date"))
    if not title or not start_raw or not end_raw:
        return None, f"конференция «{slug}» не найдена, а данных для её создания недостаточно"

    try:
        start_date = datetime.datetime.strptime(start_raw, DATE_FORMAT).date()
        end_date = datetime.datetime.strptime(end_raw, DATE_FORMAT).date()
    except ValueError:
        return None, f"конференция «{slug}»: некорректная дата ({start_raw} / {end_raw})"

    try:
        with transaction.atomic():
            conference = Conference.objects.create(
                slug=slug,
                title=title,
                location=location,
                start_date=start_date,
                end_date=end_date,
                stage=Stage.FINISHED,
            )
    except IntegrityError as exc:
        return None, f"конференция «{slug}»: не удалось создать ({exc})"

    report.created += 1
    return conference, None


def import_participations(rows):
    """Создаёт регистрации и заявки на основе истории участий.

    Возвращает три отчёта: по конференциям (создание отсутствующих в системе), по докладам
    (роль `author`) и по регистрациям (роль `participant`). Требует, чтобы пользователи уже
    были импортированы `import_users` — участник ищется по `legacy_id`.
    """
    conferences_report = ImportReport("Конференции")
    submissions_report = ImportReport("Доклады")
    registrations_report = ImportReport("Регистрации")

    for line, row in enumerate(rows, start=2):
        legacy_id = _clean(row.get("legacy_id"))
        role = _clean(row.get("role"))

        profile = (
            Profile.objects.select_related("user").filter(legacy_id=legacy_id).first()
            if legacy_id
            else None
        )
        if profile is None:
            registrations_report.skip(line, f"неизвестный участник (legacy_id={legacy_id!r})")
            continue

        conference, error = _get_or_create_conference(row, line, conferences_report)
        if conference is None:
            registrations_report.skip(line, error)
            continue

        if role == ROLE_AUTHOR:
            _import_submission(row, line, conference, profile, submissions_report)
        elif role == ROLE_PARTICIPANT:
            _import_registration(conference, profile, registrations_report)
        else:
            registrations_report.skip(line, f"неизвестная роль: {role!r}")

    return conferences_report, submissions_report, registrations_report


def _import_submission(row, line, conference, profile, report):
    title = _clean(row.get("submission_title"))
    if not title:
        report.skip(line, "роль author без submission_title")
        return

    abstract = _clean(row.get("submission_abstract"))
    status = _clean(row.get("status")) or Submission.Status.ACCEPTED
    if status not in Submission.Status.values:
        report.skip(line, f"«{title}»: неизвестный статус {status!r}")
        return

    with transaction.atomic():
        submission = Submission.objects.filter(
            conference=conference, author=profile, title=title
        ).first()
        if submission is None:
            Submission.objects.create(
                conference=conference, author=profile, title=title, abstract=abstract, status=status
            )
            report.created += 1
            return

        changed = submission.abstract != abstract or submission.status != status
        if changed:
            submission.abstract, submission.status = abstract, status
            submission.save(update_fields=["abstract", "status", "updated_at"])
            report.updated += 1
        else:
            report.unchanged += 1


def _import_registration(conference, profile, report):
    with transaction.atomic():
        _, created = Registration.objects.get_or_create(conference=conference, participant=profile)
    report.created += 1 if created else 0
    report.unchanged += 0 if created else 1

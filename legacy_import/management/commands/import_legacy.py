import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from legacy_import.services import import_participations, import_users


class _DryRunRollback(Exception):
    """Внутренний сигнал для отката транзакции в режиме --dry-run."""


def _read_rows(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise CommandError(f"Не удалось прочитать {path}: {exc}") from exc


class Command(BaseCommand):
    help = (
        "Переносит участников и историю участий из CSV старой системы. "
        "Идемпотентна: повторный запуск не создаёт дублей."
    )

    def add_arguments(self, parser):
        parser.add_argument("users_csv", help="CSV с пользователями (legacy_id, email, ...)")
        parser.add_argument(
            "participations_csv", help="CSV с историей участий (legacy_id, conference_slug, ...)"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать отчёт, но не сохранять изменения в базе.",
        )

    def handle(self, *args, **options):
        users_rows = _read_rows(options["users_csv"])
        participations_rows = _read_rows(options["participations_csv"])
        dry_run = options["dry_run"]

        try:
            with transaction.atomic():
                users_report = import_users(users_rows)
                conferences_report, submissions_report, registrations_report = (
                    import_participations(participations_rows)
                )
                if dry_run:
                    raise _DryRunRollback
        except _DryRunRollback:
            pass

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Пробный запуск (--dry-run): изменения не сохранены.\n")
            )

        for report in (users_report, conferences_report, submissions_report, registrations_report):
            style = self.style.WARNING if report.skipped else self.style.SUCCESS
            self.stdout.write(style(str(report)))
            self.stdout.write("")

"""Создаёт вымышленные демо-данные для ручной проверки интерфейса. Можно запускать повторно."""

import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts import roles
from conferences.models import Conference, Stage
from submissions.models import Submission

DEMO_PASSWORD = "demo-pass-123"

# (email, имя, фамилия, организация, страна)
ARCHIVE_AUTHORS = [
    ("talk01@example.com", "Анна", "Волкова", "Институт физики", "Россия"),
    ("talk02@example.com", "Пётр", "Морозов", "Университет Северной Долины", "Россия"),
    ("talk03@example.com", "Ирина", "Соколова", "Институт химии", "Россия"),
    ("talk04@example.com", "Ханс", "Шнайдер", "Технический институт Альпенбург", "Германия"),
    ("talk05@example.com", "Грета", "Вагнер", "Университет Рейнталь", "Германия"),
    ("talk06@example.com", "Луи", "Мартен", "Институт Бельвиль", "Франция"),
    ("talk07@example.com", "Камила", "Дюбуа", "Университет Лаванды", "Франция"),
    ("talk08@example.com", "Марко", "Росси", "Политехнический институт Порто-Верде", "Италия"),
    ("talk09@example.com", "Елена", "Кузнецова", "Институт материалов", "Россия"),
    ("talk10@example.com", "Олаф", "Нильсен", "Университет Фьордланд", "Норвегия"),
    ("talk11@example.com", "Сара", "Коэн", "Институт Тихих Холмов", "Израиль"),
    ("talk12@example.com", "Дмитрий", "Орлов", "Институт вычислительных наук", "Россия"),
]

ARCHIVE_TITLES = [
    "Квантовые вычисления на малых устройствах",
    "Новые катализаторы для органического синтеза",
    "Моделирование турбулентных течений",
    "Нейронные сети в анализе спектров",
    "Фотонные кристаллы и их применение",
    "Устойчивость распределённых систем",
    "Графеновые покрытия для сенсоров",
    "Методы оптимизации в логистике",
    "Компьютерное зрение в геологии",
    "Статистика редких событий",
    "Биоинформатика: выравнивание последовательностей",
    "Численные методы для уравнений в частных производных",
]


class Command(BaseCommand):
    help = "Создаёт вымышленные конференции, пользователей и заявки для ручной проверки."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        def user(email, first, last, group, affiliation="", country="", staff=False):
            account = User.objects.filter(email=email).first()
            if account is None:
                account = User.objects.create_user(
                    email=email,
                    password=DEMO_PASSWORD,
                    first_name=first,
                    last_name=last,
                    is_staff=staff,
                )
            account.groups.add(Group.objects.get(name=group))
            profile = account.profile
            profile.affiliation, profile.country = affiliation, country
            profile.save()
            return account

        def conference(slug, **fields):
            # Этап задаётся напрямую: это демо-данные, а не рабочий переход с записью в журнал.
            return Conference.objects.get_or_create(slug=slug, defaults=fields)[0]

        def submission(conf, author, title, status, abstract):
            return Submission.objects.get_or_create(
                conference=conf,
                author=author.profile,
                title=title,
                defaults={"abstract": abstract, "status": status},
            )[0]

        user("organizer@example.com", "Ольга", "Организаторова", roles.ORGANIZER, staff=True)
        reviewers = [
            user("reviewer1@example.com", "Роман", "Рецензентов", roles.REVIEWER),
            user("reviewer2@example.com", "Марина", "Проверкина", roles.REVIEWER),
        ]
        authors = [
            user(
                "author1@example.com",
                "Иван",
                "Авторов",
                roles.PARTICIPANT,
                "Институт физики",
                "Россия",
            ),
            user(
                "author2@example.com",
                "Мария",
                "Писарева",
                roles.PARTICIPANT,
                "Университет Лаванды",
                "Франция",
            ),
            user(
                "author3@example.com",
                "Пауль",
                "Штейн",
                roles.PARTICIPANT,
                "Институт Рейнталь",
                "Германия",
            ),
        ]

        # 1. Идёт приём заявок: можно подавать и редактировать.
        open_conf = conference(
            "conf-2026",
            title="Конференция 2026",
            description="Ежегодная научная конференция. Идёт приём заявок на доклады.",
            location="Северная Долина",
            start_date=datetime.date(2026, 11, 10),
            end_date=datetime.date(2026, 11, 12),
            stage=Stage.SUBMISSION,
        )
        submission(
            open_conf, authors[0], "Черновик доклада", Submission.Status.DRAFT, "Пока не дописан."
        )

        # 2. Идёт рецензирование: можно назначать рецензентов и принимать решения.
        review_conf = conference(
            "spring-school-2026",
            title="Весенняя школа 2026",
            description="Школа для молодых исследователей. Заявки на рецензировании.",
            location="Порто-Верде",
            start_date=datetime.date(2026, 4, 20),
            end_date=datetime.date(2026, 4, 24),
            stage=Stage.REVIEW,
        )
        submission(
            review_conf,
            authors[0],
            "Анализ данных эксперимента",
            Submission.Status.SUBMITTED,
            "Обработка результатов серии измерений.",
        )
        submission(
            review_conf,
            authors[1],
            "Метод быстрой фильтрации",
            Submission.Status.SUBMITTED,
            "Новый подход к фильтрации шума.",
        )
        submission(
            review_conf,
            authors[2],
            "Обзор современных подходов",
            Submission.Status.SUBMITTED,
            "Сравнение существующих методов.",
        )
        submission(
            review_conf,
            authors[2],
            "Незавершённая работа",
            Submission.Status.DRAFT,
            "Автор ещё не отправил.",
        )

        # 3. Завершённая конференция с принятыми докладами: программа, поиск, пагинация.
        archive = conference(
            "conf-2025",
            title="Конференция 2025",
            description="Архивная конференция с опубликованной программой.",
            location="Альпенбург",
            start_date=datetime.date(2025, 10, 5),
            end_date=datetime.date(2025, 10, 7),
            stage=Stage.FINISHED,
        )
        for (email, first, last, affiliation, country), title in zip(
            ARCHIVE_AUTHORS, ARCHIVE_TITLES, strict=True
        ):
            author = user(email, first, last, roles.PARTICIPANT, affiliation, country)
            submission(
                archive, author, title, Submission.Status.ACCEPTED, f"Доклад: {title.lower()}."
            )

        self.stdout.write(self.style.SUCCESS("Демо-данные готовы."))
        self.stdout.write(f"Пароль у всех демо-пользователей: {DEMO_PASSWORD}")
        self.stdout.write("  organizer@example.com   — оргкомитет (панель, админка)")
        self.stdout.write(f"  {reviewers[0].email}  — рецензент")
        self.stdout.write(f"  {reviewers[1].email}  — рецензент")
        self.stdout.write("  author1@example.com     — участник (author2, author3 — тоже)")

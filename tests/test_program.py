"""Публичная программа: только принятые доклады, поиск, фильтр, фрагменты HTMX, пагинация."""

from urllib.parse import quote

import pytest
from django.urls import reverse

from submissions.models import Submission

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def conference(make_conference):
    return make_conference(slug="prog-conf", title="Конференция программы")


@pytest.fixture
def make_talk(make_user, conference):
    """Фабрика докладов вместе с авторами: `make_talk("Название", last_name="Иванов")`."""
    counter = {"n": 0}

    def _make(
        title, status=Submission.Status.ACCEPTED, conf=None, last_name="Автор", country="", **extra
    ):
        counter["n"] += 1
        user = make_user(f"talk{counter['n']}@example.com", last_name=last_name, first_name="Иван")
        profile = user.profile
        profile.country = country
        profile.affiliation = extra.pop("affiliation", "")
        profile.save()
        return Submission.objects.create(
            conference=conf or conference,
            author=profile,
            title=title,
            abstract=extra.pop("abstract", "Описание доклада"),
            status=status,
        )

    return _make


def url(conference):
    return reverse("conference_program", args=[conference.slug])


def test_program_is_public_and_lists_only_accepted_talks(client, conference, make_talk):
    make_talk("Принятый доклад")
    make_talk("Черновик", status=Submission.Status.DRAFT)
    make_talk("Поданный доклад", status=Submission.Status.SUBMITTED)
    make_talk("Отклонённый доклад", status=Submission.Status.REJECTED)

    content = client.get(url(conference)).content.decode()

    assert "Принятый доклад" in content
    for hidden in ("Черновик", "Поданный доклад", "Отклонённый доклад"):
        assert hidden not in content


def test_program_shows_only_talks_of_this_conference(
    client, conference, make_conference, make_talk
):
    other = make_conference(slug="other")
    make_talk("Здесь", conf=conference)
    make_talk("Там", conf=other)

    content = client.get(url(conference)).content.decode()

    assert "Здесь" in content
    assert "Там" not in content


def test_unknown_conference_program_returns_404(client, db):
    assert client.get(reverse("conference_program", args=["nope"])).status_code == 404


def test_search_by_title(client, conference, make_talk):
    make_talk("Квантовые вычисления")
    make_talk("Органический синтез")

    content = client.get(url(conference), {"q": "квант"}).content.decode()

    assert "Квантовые вычисления" in content
    assert "Органический синтез" not in content


def test_search_by_abstract(client, conference, make_talk):
    make_talk("Первый", abstract="Про нейронные сети")
    make_talk("Второй", abstract="Про геологию")

    content = client.get(url(conference), {"q": "нейронные"}).content.decode()

    assert "Первый" in content
    assert "Второй" not in content


def test_search_by_author_last_name(client, conference, make_talk):
    make_talk("Доклад А", last_name="Кузнецов")
    make_talk("Доклад Б", last_name="Смирнов")

    content = client.get(url(conference), {"q": "кузнецов"}).content.decode()

    assert "Доклад А" in content
    assert "Доклад Б" not in content


def test_filter_by_country(client, conference, make_talk):
    make_talk("Из России", country="Россия")
    make_talk("Из Франции", country="Франция")

    content = client.get(url(conference), {"country": "Франция"}).content.decode()

    assert "Из Франции" in content
    assert "Из России" not in content


def test_search_and_country_combine(client, conference, make_talk):
    make_talk("Физика в России", country="Россия")
    make_talk("Химия в России", country="Россия")
    make_talk("Физика во Франции", country="Франция")

    content = client.get(url(conference), {"q": "физика", "country": "Россия"}).content.decode()

    assert "Физика в России" in content
    assert "Химия в России" not in content
    assert "Физика во Франции" not in content


def test_unknown_country_is_ignored_instead_of_hiding_everything(client, conference, make_talk):
    make_talk("Доклад", country="Россия")

    content = client.get(url(conference), {"country": "Атлантида"}).content.decode()

    assert "Доклад" in content


def test_country_choices_list_only_countries_of_accepted_authors(client, conference, make_talk):
    make_talk("Принят", country="Россия")
    make_talk("Отклонён", country="Бразилия", status=Submission.Status.REJECTED)

    content = client.get(url(conference)).content.decode()

    assert 'value="Россия"' in content
    assert "Бразилия" not in content


def test_nothing_found_message(client, conference, make_talk):
    make_talk("Доклад")

    content = client.get(url(conference), {"q": "несуществующее"}).content.decode()

    assert "Ничего не найдено" in content


def test_htmx_request_returns_only_results_fragment(client, conference, make_talk):
    make_talk("Доклад")

    response = client.get(url(conference), {"q": "доклад"}, **HTMX)

    content = response.content.decode()
    assert "<html" not in content
    assert "<form" not in content
    assert "Доклад" in content


def test_plain_request_returns_full_page_with_filter_form(client, conference, make_talk):
    make_talk("Доклад")

    content = client.get(url(conference)).content.decode()

    assert "<html" in content
    assert 'hx-target="#program-results"' in content


def test_history_restore_request_returns_full_page(client, conference, make_talk):
    # Кнопка «Назад»: HTMX запрашивает страницу целиком, фрагмент сломал бы её.
    make_talk("Доклад")

    response = client.get(
        url(conference), HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true"
    )

    assert "<html" in response.content.decode()


def test_pagination_splits_results_and_keeps_filters(client, conference, make_talk):
    for number in range(12):
        make_talk(f"Доклад номер {number:02d}", country="Россия")

    first = client.get(url(conference), {"country": "Россия"}).content.decode()
    second = client.get(url(conference), {"country": "Россия", "page": 2}).content.decode()

    assert first.count('class="talk"') == 10
    assert second.count('class="talk"') == 2
    # Ссылка на следующую страницу сохраняет выбранный фильтр (в HTML & экранируется).
    assert f"country={quote('Россия')}&amp;page=2" in first


def test_out_of_range_page_falls_back_to_last_page(client, conference, make_talk):
    make_talk("Единственный доклад")

    response = client.get(url(conference), {"page": 999})

    assert response.status_code == 200
    assert "Единственный доклад" in response.content.decode()


def test_query_count_does_not_grow_with_number_of_talks(
    client, conference, make_talk, django_assert_max_num_queries
):
    for number in range(10):
        make_talk(f"Доклад {number}", country="Россия")

    # Пагинатор (COUNT), страны для фильтра, страница докладов с авторами: без N+1.
    with django_assert_max_num_queries(4):
        client.get(url(conference))


def test_author_email_is_not_exposed(client, conference, make_talk):
    make_talk("Доклад")

    content = client.get(url(conference)).content.decode()

    assert "@example.com" not in content


def test_conference_page_links_to_program(client, conference):
    content = client.get(reverse("conference_detail", args=[conference.slug])).content.decode()

    assert url(conference) in content

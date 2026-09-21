from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from submissions import selectors
from submissions.forms import ProgramFilterForm

from .models import Conference

PROGRAM_PAGE_SIZE = 10


def home(request):
    """Главная: список конференций, свежие сверху."""
    return render(request, "conferences/home.html", {"conferences": Conference.objects.all()})


def detail(request, slug):
    """Публичная страница конференции."""
    conference = get_object_or_404(Conference, slug=slug)
    return render(request, "conferences/detail.html", {"conference": conference})


def program(request, slug):
    """Публичная программа: принятые доклады с поиском и фильтром.

    Запрос HTMX получает только список; при восстановлении истории браузером
    (кнопка «Назад») HTMX просит страницу целиком, поэтому отдаём её.
    """
    conference = get_object_or_404(Conference, slug=slug)
    form = ProgramFilterForm(request.GET, selectors.program_countries(conference))
    submissions = selectors.search_program(conference, **form.filters())
    page = Paginator(submissions, PROGRAM_PAGE_SIZE).get_page(request.GET.get("page"))

    # Адрес страницы без номера страницы: к нему добавляются ссылки пагинации.
    query = request.GET.copy()
    query.pop("page", None)

    context = {
        "conference": conference,
        "form": form,
        "page": page,
        "querystring": query.urlencode(),
    }
    fragment = request.htmx and not request.htmx.history_restore_request
    template = "conferences/_program_results.html" if fragment else "conferences/program.html"
    return render(request, template, context)

"""Выборки для чтения (в отличие от services.py, ничего не меняют)."""

from django.db.models import Q

from accounts.models import Profile

from .models import Submission


def accepted_submissions(conference):
    """Принятые доклады конференции с автором одним запросом."""
    return (
        Submission.objects.filter(conference=conference, status=Submission.Status.ACCEPTED)
        .select_related("author__user")
        .order_by("title")
    )


def program_countries(conference):
    """Страны авторов принятых докладов — варианты для фильтра."""
    return list(
        Profile.objects.filter(
            submissions__conference=conference,
            submissions__status=Submission.Status.ACCEPTED,
        )
        .exclude(country="")
        .values_list("country", flat=True)
        .distinct()
        .order_by("country")
    )


def search_program(conference, query="", country=""):
    """Принятые доклады с поиском по названию, аннотации и имени автора и фильтром по стране."""
    submissions = accepted_submissions(conference)
    if query:
        submissions = submissions.filter(
            Q(title__icontains=query)
            | Q(abstract__icontains=query)
            | Q(author__user__first_name__icontains=query)
            | Q(author__user__last_name__icontains=query)
        )
    if country:
        submissions = submissions.filter(author__country=country)
    return submissions

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import services
from .forms import ReviewForm
from .models import Review
from .services import ReviewError

# Автор заявки рецензенту не показывается (слепое рецензирование), поэтому в выборках
# нет данных об авторе.


def reviewer_only(view):
    """Нужен вход и право менять рецензии (есть у ролей «Рецензент» и «Оргкомитет»)."""
    return login_required(permission_required("reviews.change_review", raise_exception=True)(view))


@reviewer_only
def review_list(request):
    reviews = Review.objects.filter(reviewer=request.user).select_related("submission__conference")
    return render(request, "reviews/list.html", {"reviews": reviews})


@reviewer_only
def review_detail(request, pk):
    review = get_object_or_404(
        Review.objects.select_related("submission__conference"), pk=pk, reviewer=request.user
    )
    error = saved = False
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                services.save_review(review, **form.cleaned_data)
            except ReviewError as exc:
                error = str(exc)
            else:
                saved = True
                if not request.htmx:
                    messages.success(request, "Рецензия сохранена.")
                    return redirect(reverse("review_detail", args=[pk]))
    else:
        form = ReviewForm(initial={"score": review.score, "comment": review.comment})

    context = {
        "review": review,
        "form": form,
        "error": error,
        "saved": saved,
        "open": review.submission.conference.reviews_open,
    }
    template = "reviews/_panel.html" if request.htmx else "reviews/detail.html"
    return render(request, template, context)

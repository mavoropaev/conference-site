from django.urls import path

from . import views

urlpatterns = [
    path("submissions/", views.submission_list, name="submission_list"),
    path("submissions/<int:pk>/", views.submission_detail, name="submission_detail"),
    path("submissions/<int:pk>/edit/", views.submission_edit, name="submission_edit"),
    path("submissions/<int:pk>/submit/", views.submission_submit, name="submission_submit"),
    path(
        "conferences/<slug:slug>/submissions/new/",
        views.submission_create,
        name="submission_create",
    ),
]

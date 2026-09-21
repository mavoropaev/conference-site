from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("conferences/<slug:slug>/", views.detail, name="conference_detail"),
    path("conferences/<slug:slug>/program/", views.program, name="conference_program"),
]

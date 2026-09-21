from django.urls import path

from . import views

urlpatterns = [
    path("organizer/", views.dashboard, name="organizer_dashboard"),
    path("organizer/submissions/<int:pk>/assign/", views.assign_reviewer, name="organizer_assign"),
    path("organizer/submissions/<int:pk>/decide/", views.decide, name="organizer_decide"),
    path("organizer/<slug:slug>/", views.panel, name="organizer_panel"),
    path("organizer/<slug:slug>/stage/advance/", views.stage_advance, name="organizer_advance"),
    path("organizer/<slug:slug>/stage/revert/", views.stage_revert, name="organizer_revert"),
]

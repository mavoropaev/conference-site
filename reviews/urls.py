from django.urls import path

from . import views

urlpatterns = [
    path("reviews/", views.review_list, name="review_list"),
    path("reviews/<int:pk>/", views.review_detail, name="review_detail"),
]

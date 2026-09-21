from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("submission", "reviewer", "score", "created_at")
    list_filter = ("submission__conference", "score")
    search_fields = ("submission__title", "reviewer__email")
    list_select_related = ("submission", "reviewer")
    raw_id_fields = ("submission", "reviewer")

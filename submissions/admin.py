from django.contrib import admin

from .models import Registration, Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "conference", "author", "status", "created_at")
    list_filter = ("conference", "status")
    search_fields = ("title", "author__user__email", "author__user__last_name")
    list_select_related = ("conference", "author__user")
    raw_id_fields = ("author",)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("participant", "conference", "created_at")
    list_filter = ("conference",)
    search_fields = ("participant__user__email", "participant__user__last_name")
    list_select_related = ("conference", "participant__user")
    raw_id_fields = ("participant",)

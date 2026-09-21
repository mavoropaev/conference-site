from django.contrib import admin, messages

from .models import Conference, StageTransition, StageTransitionError


class StageTransitionInline(admin.TabularInline):
    """Журнал переходов внутри карточки конференции — только для чтения."""

    model = StageTransition
    extra = 0
    fields = ("created_at", "from_stage", "to_stage", "changed_by", "reason")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("title", "start_date", "end_date", "stage")
    list_filter = ("stage",)
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    # Этап нельзя править напрямую: только через действие ниже, чтобы остался след в журнале.
    readonly_fields = ("stage", "created_at")
    inlines = [StageTransitionInline]
    actions = ["advance_stage"]

    def has_manage_stage_permission(self, request):
        return request.user.has_perm("conferences.manage_stage")

    @admin.action(description="Перевести на следующий этап", permissions=["manage_stage"])
    def advance_stage(self, request, queryset):
        for conference in queryset:
            try:
                conference.advance(by=request.user)
            except StageTransitionError as exc:
                self.message_user(request, f"{conference}: {exc}", messages.ERROR)
            else:
                self.message_user(
                    request,
                    f"{conference}: теперь этап «{conference.get_stage_display()}».",
                    messages.SUCCESS,
                )

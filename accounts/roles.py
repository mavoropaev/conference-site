"""Роли сайта. Роль — это группа Django с набором прав.

Группы создаются обработчиком `post_migrate` (см. `accounts/apps.py`), поэтому они есть
после любого `migrate`, в том числе в тестовой БД. Обработчик идемпотентный.
Состав ролей описан в коде и является источником истины: при каждом `migrate` права группы
приводятся к этому списку, ручные правки прав этих групп в админке будут перезаписаны.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q

PARTICIPANT = "Участник"
REVIEWER = "Рецензент"
ORGANIZER = "Оргкомитет"

# Права записаны как "<приложение>.<кодовое имя>".
ROLE_PERMISSIONS = {
    # Участник: доступ к своим заявкам и регистрациям определяется владением объектом
    # во вьюхах, а не глобальными правами.
    PARTICIPANT: [],
    REVIEWER: [
        "reviews.view_review",
        "reviews.change_review",
        "submissions.view_submission",
    ],
    ORGANIZER: [
        "conferences.view_conference",
        "conferences.change_conference",
        "conferences.manage_stage",
        "conferences.revert_stage",
        "submissions.view_submission",
        "submissions.change_submission",
        "submissions.decide_submission",
        "submissions.view_registration",
        "submissions.change_registration",
        "reviews.view_review",
        "reviews.add_review",
        "reviews.change_review",
        "reviews.assign_reviewer",
    ],
}


def sync_roles(using="default"):
    """Создаёт группы ролей и приводит их права к `ROLE_PERMISSIONS`."""
    # Права других приложений создаются их собственным post_migrate, который на момент
    # вызова этого обработчика мог ещё не отработать, поэтому создаём права заранее.
    for app_config in global_apps.get_app_configs():
        create_permissions(app_config, verbosity=0, using=using)

    for role, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.using(using).get_or_create(name=role)

        query = Q()
        for full_name in codenames:
            app_label, codename = full_name.split(".")
            query |= Q(content_type__app_label=app_label, codename=codename)
        permissions = Permission.objects.using(using).filter(query) if codenames else []

        if len(permissions) != len(codenames):
            found = {f"{p.content_type.app_label}.{p.codename}" for p in permissions}
            missing = sorted(set(codenames) - found)
            raise ImproperlyConfigured(f"Роль «{role}»: не найдены права {missing}.")

        group.permissions.set(permissions)

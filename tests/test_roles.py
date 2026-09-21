"""Роли: группы создаются миграцией и дают ровно те права, что описаны в коде."""

import pytest
from django.contrib.auth.models import Group

from accounts import roles
from accounts.roles import ROLE_PERMISSIONS, sync_roles
from conferences.models import Stage


def group_permissions(group_name):
    group = Group.objects.get(name=group_name)
    return {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.all()}


@pytest.mark.django_db
@pytest.mark.parametrize("role", [roles.PARTICIPANT, roles.REVIEWER, roles.ORGANIZER])
def test_role_group_exists_after_migrate(role):
    assert Group.objects.filter(name=role).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(ROLE_PERMISSIONS))
def test_role_has_exactly_declared_permissions(role):
    assert group_permissions(role) == set(ROLE_PERMISSIONS[role])


@pytest.mark.django_db
def test_sync_is_idempotent():
    sync_roles()
    sync_roles()

    assert Group.objects.filter(name=roles.ORGANIZER).count() == 1
    assert group_permissions(roles.ORGANIZER) == set(ROLE_PERMISSIONS[roles.ORGANIZER])


@pytest.mark.django_db
def test_sync_restores_manually_removed_permission():
    group = Group.objects.get(name=roles.ORGANIZER)
    group.permissions.clear()

    sync_roles()

    assert group_permissions(roles.ORGANIZER) == set(ROLE_PERMISSIONS[roles.ORGANIZER])


def test_organizer_can_manage_stages(make_user, make_conference):
    organizer = make_user("org@example.com")
    organizer.groups.add(Group.objects.get(name=roles.ORGANIZER))
    conference = make_conference()

    conference.advance(by=organizer)
    conference.revert(by=organizer, reason="Ошибка в сроках")

    assert conference.stage == Stage.SUBMISSION


def test_reviewer_and_participant_cannot_manage_stages(make_user):
    reviewer = make_user("rev@example.com")
    reviewer.groups.add(Group.objects.get(name=roles.REVIEWER))
    participant = make_user("part@example.com")
    participant.groups.add(Group.objects.get(name=roles.PARTICIPANT))

    for user in (reviewer, participant):
        assert not user.has_perm("conferences.manage_stage")
        assert not user.has_perm("conferences.revert_stage")


def test_only_organizer_can_assign_reviewers_and_decide(make_user):
    organizer = make_user("org@example.com")
    organizer.groups.add(Group.objects.get(name=roles.ORGANIZER))
    reviewer = make_user("rev@example.com")
    reviewer.groups.add(Group.objects.get(name=roles.REVIEWER))

    assert organizer.has_perm("reviews.assign_reviewer")
    assert organizer.has_perm("submissions.decide_submission")
    assert not reviewer.has_perm("reviews.assign_reviewer")
    assert not reviewer.has_perm("submissions.decide_submission")

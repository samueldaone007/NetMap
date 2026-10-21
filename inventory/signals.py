"""Automatic change journal.

Every save and delete on an inventory model writes one or more ChangeLog rows.
The current request user is picked up from a context variable set by
CurrentUserMiddleware, so views and the admin both attribute changes.
"""
from __future__ import annotations

from datetime import date, datetime

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .middleware import get_current_user
from .models import (
    ChangeLog,
    Connection,
    Device,
    IPAddress,
    Location,
    Outage,
    Port,
    Subnet,
)

TRACKED_MODELS = (Location, Subnet, Device, IPAddress, Port, Connection, Outage)
TRACKED_NAMES = {model.__name__ for model in TRACKED_MODELS}

EXCLUDED_FIELDS = {
    "id",
    "pk",
    "created_at",
    "updated_at",
    "import_fingerprint",
    "graph_x",
    "graph_y",
}


def _is_tracked(sender) -> bool:
    return sender in TRACKED_MODELS


def _display_value(instance, field, value) -> str:
    if value is None:
        return ""
    if field.is_relation:
        return str(value.pk) if value is not None else ""
    if field.choices:
        display = dict(field.choices).get(value, value)
        return str(display)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    text = str(value)
    return text if len(text) <= 2000 else f"{text[:1997]}…"


def _old_display(old_instance, field) -> str:
    if old_instance is None:
        return ""
    value = getattr(old_instance, field.name)
    if field.is_relation:
        return _display_value(old_instance, field, value)
    return _display_value(old_instance, field, value)


def _new_display(instance, field) -> str:
    return _display_value(instance, field, getattr(instance, field.name))


@receiver(pre_save)
def capture_previous_state(sender, instance, **kwargs):
    if not _is_tracked(sender) or not instance.pk:
        instance._netmap_old = None
        return
    try:
        instance._netmap_old = sender._default_manager.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._netmap_old = None


@receiver(post_save)
def write_change_log(sender, instance, created, **kwargs):
    if not _is_tracked(sender):
        return
    user = get_current_user()
    object_type = sender.__name__
    object_repr = str(instance)[:240]
    if created:
        ChangeLog.objects.create(
            object_type=object_type,
            object_id=str(instance.pk),
            object_repr=object_repr,
            action=ChangeLog.Action.CREATE,
            field="",
            old_value="",
            new_value=object_repr,
            user=user,
        )
        return

    old_instance = getattr(instance, "_netmap_old", None)
    if old_instance is None:
        return

    update_fields = kwargs.get("update_fields")
    if update_fields is not None:
        allowed = set(update_fields)
    else:
        allowed = None

    rows = []
    for field in sender._meta.concrete_fields:
        if field.name in EXCLUDED_FIELDS or field.primary_key:
            continue
        if allowed is not None and field.name not in allowed:
            continue
        old_value = _old_display(old_instance, field)
        new_value = _new_display(instance, field)
        if old_value != new_value:
            rows.append(
                ChangeLog(
                    object_type=object_type,
                    object_id=str(instance.pk),
                    object_repr=object_repr,
                    action=ChangeLog.Action.UPDATE,
                    field=field.name,
                    old_value=old_value,
                    new_value=new_value,
                    user=user,
                )
            )
    if rows:
        ChangeLog.objects.bulk_create(rows)


@receiver(pre_delete)
def write_delete_log(sender, instance, **kwargs):
    if not _is_tracked(sender):
        return
    ChangeLog.objects.create(
        object_type=sender.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance)[:240],
        action=ChangeLog.Action.DELETE,
        field="",
        old_value=str(instance)[:2000],
        new_value="",
        user=get_current_user(),
    )

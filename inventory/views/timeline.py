"""The service record: changes, outages and their management."""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..forms import OutageForm
from ..models import ChangeLog, Outage

RECORD_TYPES = [
    ("Device", "Devices"),
    ("Connection", "Connections"),
    ("Subnet", "Subnets"),
    ("IPAddress", "IP addresses"),
    ("Port", "Ports"),
    ("Location", "Locations"),
    ("Outage", "Outages"),
]
RECORD_LABELS = dict(RECORD_TYPES)


def _duration_label(seconds: int) -> str:
    if seconds < 60:
        return f"{max(seconds, 1)}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        remainder = minutes % 60
        return f"{hours}h {remainder:02d}m" if remainder else f"{hours}h"
    days = hours // 24
    remainder = hours % 24
    return f"{days}d {remainder:02d}h" if remainder else f"{days}d"


def _outage_duration(outage):
    end = outage.ended or timezone.now()
    seconds = max(int((end - outage.started).total_seconds()), 1)
    return _duration_label(seconds)


def _outage_subject(outage):
    if outage.device_id:
        return outage.device.name
    connection = outage.connection
    far_end = (
        f"{connection.port_b.device.name}:{connection.port_b.label}"
        if connection.port_b
        else "Unknown"
    )
    return f"{connection.port_a.device.name}:{connection.port_a.label} ↔ {far_end}"


def _outage_href(outage):
    if outage.device_id:
        return reverse("device_detail", args=[outage.device_id])
    connection = outage.connection
    query = connection.cable_label or connection.port_a.device.name
    return f"{reverse('connection_list')}?{urlencode({'q': query})}"


def _object_href(entry):
    if entry.action == ChangeLog.Action.DELETE:
        return ""
    routes = {
        "Device": ("device_detail", True),
        "Subnet": ("subnet_detail", True),
        "IPAddress": ("ip_list", False),
        "Port": ("port_list", False),
        "Connection": ("connection_list", False),
    }
    route = routes.get(entry.object_type)
    if not route:
        return ""
    name, uses_pk = route
    try:
        if uses_pk:
            return reverse(name, args=[entry.object_id])
        return f"{reverse(name)}?{urlencode({'q': entry.object_repr})}"
    except (NoReverseMatch, ValueError):
        return ""


def _events(record: str, search: str):
    changes = ChangeLog.objects.select_related("user").exclude(object_type="Outage")
    outages = Outage.objects.select_related(
        "device", "connection__port_a__device", "connection__port_b__device"
    )
    if record == "Outage":
        changes = changes.none()
    elif record in RECORD_LABELS:
        changes = changes.filter(object_type=record)
        outages = outages.none()

    if search:
        changes = changes.filter(
            Q(object_repr__icontains=search)
            | Q(field__icontains=search)
            | Q(old_value__icontains=search)
            | Q(new_value__icontains=search)
            | Q(user__username__icontains=search)
        )
        outages = outages.filter(
            Q(cause__icontains=search)
            | Q(notes__icontains=search)
            | Q(device__name__icontains=search)
            | Q(connection__cable_label__icontains=search)
            | Q(connection__port_a__device__name__icontains=search)
            | Q(connection__port_b__device__name__icontains=search)
        )

    events = []
    for entry in changes:
        events.append(
            {
                "timestamp": entry.timestamp,
                "kind": "change",
                "kind_label": "Change",
                "action": entry.action,
                "action_label": entry.get_action_display(),
                "title": entry.object_repr,
                "object_type": entry.object_type,
                "field": entry.field.replace("_", " ") if entry.field else "",
                "old_value": entry.old_value,
                "new_value": entry.new_value,
                "user": entry.user.username if entry.user else "system",
                "href": _object_href(entry),
            }
        )
    for outage in outages:
        events.append(
            {
                "timestamp": outage.started,
                "kind": "outage",
                "kind_label": "Outage",
                "action": "open" if outage.is_open else "closed",
                "action_label": "Open" if outage.is_open else "Closed",
                "title": outage.cause,
                "object_type": "Outage",
                "subject": _outage_subject(outage),
                "href": _outage_href(outage),
                "outage": outage,
                "duration": _outage_duration(outage),
                "open": outage.is_open,
                "user": "",
            }
        )
    events.sort(key=lambda event: event["timestamp"], reverse=True)
    return events


def _group_events(events):
    groups = []
    for event in events:
        day = timezone.localtime(event["timestamp"]).date()
        if not groups or groups[-1]["day"] != day:
            groups.append({"day": day, "events": []})
        groups[-1]["events"].append(event)
    return groups


@login_required
def timeline(request):
    record = request.GET.get("record", "").strip()
    search = request.GET.get("q", "").strip()
    events = _events(record, search)
    paginator = Paginator(events, 36)
    page = paginator.get_page(request.GET.get("page"))
    page_events = list(page.object_list)
    now = timezone.now()
    open_outages = list(
        Outage.objects.filter(ended__isnull=True)
        .select_related(
            "device", "connection__port_a__device", "connection__port_b__device"
        )
        .order_by("started")
    )
    for outage in open_outages:
        outage.subject_label = _outage_subject(outage)
        outage.subject_href = _outage_href(outage)
        outage.duration_label = _outage_duration(outage)

    return render(
        request,
        "inventory/timeline.html",
        {
            "groups": _group_events(page_events),
            "page": page,
            "record": record,
            "record_types": RECORD_TYPES,
            "search": search,
            "event_total": len(events),
            "open_outages": open_outages,
            "stats": {
                "open": len(open_outages),
                "outages_30d": Outage.objects.filter(
                    started__gte=now - timedelta(days=30)
                ).count(),
                "changes_7d": ChangeLog.objects.filter(
                    timestamp__gte=now - timedelta(days=7)
                ).count(),
            },
        },
    )


@login_required
def outage_create(request):
    initial = {"started": timezone.localtime().strftime("%Y-%m-%dT%H:%M")}
    device_id = request.GET.get("device", "").strip()
    connection_id = request.GET.get("connection", "").strip()
    if device_id.isdigit():
        initial["device"] = int(device_id)
    if connection_id.isdigit():
        initial["connection"] = int(connection_id)

    if request.method == "POST":
        form = OutageForm(request.POST)
        if form.is_valid():
            outage = form.save()
            messages.success(request, f"Logged outage: {_outage_subject(outage)}.")
            if outage.device_id:
                return redirect("device_detail", pk=outage.device_id)
            return redirect("timeline")
    else:
        form = OutageForm(initial=initial)
    return render(
        request,
        "inventory/outage_form.html",
        {"form": form, "form_title": "Log an outage", "is_new": True},
    )


@login_required
def outage_edit(request, pk):
    outage = get_object_or_404(
        Outage.objects.select_related(
            "device", "connection__port_a__device", "connection__port_b__device"
        ),
        pk=pk,
    )
    if request.method == "POST":
        form = OutageForm(request.POST, instance=outage)
        if form.is_valid():
            outage = form.save()
            messages.success(request, "Outage updated.")
            if outage.device_id:
                return redirect("device_detail", pk=outage.device_id)
            return redirect("timeline")
    else:
        form = OutageForm(instance=outage)
    return render(
        request,
        "inventory/outage_form.html",
        {
            "form": form,
            "form_title": "Edit outage",
            "outage": outage,
            "is_new": False,
        },
    )


@login_required
@require_POST
def outage_close(request, pk):
    outage = get_object_or_404(Outage, pk=pk)
    next_url = request.POST.get("next", "")
    if outage.is_open:
        outage.ended = timezone.now()
        outage.save(update_fields=["ended"])
        messages.success(request, f"Closed outage: {_outage_subject(outage)}.")
    else:
        messages.info(request, "That outage is already closed.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    if outage.device_id:
        return redirect("device_detail", pk=outage.device_id)
    return redirect("timeline")

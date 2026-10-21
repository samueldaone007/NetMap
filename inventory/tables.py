"""Table definitions and rendering helpers.

The four spreadsheet-style views share one engine: columns, filters, search,
sorting, pagination and inline cell editing are described declaratively here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from .models import Connection, Device, IPAddress, Port, Subnet


BADGE_CLASSES = {
    "active": "badge-active",
    "up": "badge-up",
    "used": "badge-used",
    "in_use": "badge-up",
    "free": "badge-free",
    "spare": "badge-spare",
    "reserved": "badge-reserved",
    "retired": "badge-retired",
    "down": "badge-down",
    "unknown": "badge-unknown",
    "manual": "badge-silent",
    "import": "badge-import",
    "discovery": "badge-silent",
}


@dataclass
class Column:
    key: str
    label: str
    field: str | None = None
    kind: str = "text"
    editable: bool = False
    sortable: bool = True
    mono: bool = False
    width: str = ""
    compute: Callable | None = None
    badge: bool = False
    empty: str = "—"


@dataclass
class Filter:
    param: str
    label: str
    lookup: str
    choices: list | Callable


@dataclass
class TableConfig:
    kind: str
    title: str
    singular: str
    model: type
    columns: list[Column]
    queryset: Callable
    search_fields: list[str]
    filters: list[Filter] = field(default_factory=list)
    default_sort: str = "pk"
    default_dir: str = "asc"
    paste_fields: list[str] = field(default_factory=list)
    form_fields: list[str] = field(default_factory=list)
    description: str = ""
    empty_title: str = ""
    empty_body: str = ""
    select_related: list[str] = field(default_factory=list)
    prefetch_related: list[str] = field(default_factory=list)


def _format_value(instance, column: Column) -> str:
    if column.compute:
        value = column.compute(instance)
    else:
        value = getattr(instance, column.field)
        if column.kind == "choice":
            value = getattr(instance, f"get_{column.field}_display")()
        elif column.kind == "fk":
            value = str(value) if value else ""
        elif column.kind == "bool":
            value = "Yes" if value else "No"
        elif isinstance(value, (date, datetime)):
            value = value.strftime("%Y-%m-%d")
    if value is None or value == "":
        return column.empty
    return str(value)


def _port_usage(device):
    used, total = device.port_usage()
    return f"{used} / {total}"


def _connected_to(port):
    connections = port.connection_list
    if not connections:
        return ""
    names = []
    for connection in connections:
        other = connection.port_b if connection.port_a_id == port.pk else connection.port_a
        if other is None:
            names.append("Unknown")
        else:
            names.append(f"{other.device.name}:{other.label}")
    return ", ".join(names)


def _connection_a(connection):
    return f"{connection.port_a.device.name}:{connection.port_a.label}"


def _connection_b(connection):
    if connection.port_b_id:
        return f"{connection.port_b.device.name}:{connection.port_b.label}"
    return "Unknown"


def _count_related(instance, attr):
    return getattr(instance, attr).count()


DEVICE_CONFIG = TableConfig(
    kind="devices",
    title="Devices",
    singular="device",
    model=Device,
    description="Every station on the network, whether identified or still a sketch.",
    queryset=lambda: Device.objects.select_related("location").prefetch_related(
        "ports__connections_a", "ports__connections_b", "outages"
    ),
    search_fields=[
        "name",
        "asset_id",
        "serial_number",
        "hostname",
        "management_ip",
        "vendor",
        "model",
        "purpose",
    ],
    default_sort="name",
    paste_fields=[
        "name",
        "device_type",
        "vendor",
        "model",
        "serial_number",
        "asset_id",
        "management_ip",
        "owner",
        "status",
        "location",
    ],
    form_fields=[
        "name",
        "device_type",
        "vendor",
        "model",
        "serial_number",
        "asset_id",
        "hostname",
        "os_version",
        "firmware",
        "management_ip",
        "location",
        "owner",
        "purpose",
        "purchase_date",
        "warranty_expiry",
        "status",
        "notes",
        "needs_identifying",
        "last_verified",
    ],
    filters=[
        Filter("type", "Device type", "device_type", list(Device.Type.choices)),
        Filter("status", "Status", "status", list(Device.Status.choices)),
        Filter("site", "Site", "location__site", []),
        Filter(
            "attention",
            "Identification",
            "needs_identifying",
            [("1", "Needs identifying"), ("0", "Identified")],
        ),
    ],
    columns=[
        Column("name", "Device", "name", editable=True, width="220px"),
        Column("type", "Type", "device_type", kind="choice", editable=True, badge=True),
        Column("vendor", "Vendor", "vendor", editable=True),
        Column("model", "Model", "model", editable=True),
        Column("management_ip", "Mgmt IP", "management_ip", editable=True, mono=True),
        Column("location", "Location", "location", kind="fk", editable=True),
        Column("status", "Status", "status", kind="choice", editable=True, badge=True),
        Column("ports", "Ports", compute=_port_usage, sortable=False, mono=True, width="80px"),
        Column("flag", "Identify", "needs_identifying", kind="bool", editable=True, width="80px"),
        Column("source", "Source", "source", kind="choice", badge=True),
    ],
    empty_title="No devices on this line yet",
    empty_body="Add a device or paste a block of rows straight from your spreadsheet.",
)

IP_CONFIG = TableConfig(
    kind="ips",
    title="IP addresses",
    singular="IP address",
    model=IPAddress,
    description="The address ledger. Free and reserved addresses stay visible on purpose.",
    queryset=lambda: IPAddress.objects.select_related("subnet", "device"),
    search_fields=["address", "hostname", "device__name", "subnet__name", "subnet__cidr"],
    default_sort="address",
    paste_fields=["address", "subnet", "device", "hostname", "status"],
    form_fields=[
        "address",
        "subnet",
        "device",
        "hostname",
        "status",
        "source",
        "last_verified",
    ],
    filters=[
        Filter("status", "Status", "status", list(IPAddress.Status.choices)),
        Filter("subnet", "Subnet", "subnet_id", []),
    ],
    columns=[
        Column("address", "Address", "address", editable=True, mono=True),
        Column("subnet", "Subnet", "subnet", kind="fk", editable=True),
        Column("device", "Device", "device", kind="fk", editable=True),
        Column("hostname", "Hostname", "hostname", editable=True),
        Column("status", "Status", "status", kind="choice", editable=True, badge=True),
        Column("source", "Source", "source", kind="choice", badge=True),
        Column("verified", "Verified", "last_verified", kind="date", editable=True),
    ],
    empty_title="The address ledger is blank",
    empty_body="Paste an IP list or reserve the first address on a subnet.",
)

PORT_CONFIG = TableConfig(
    kind="ports",
    title="Ports",
    singular="port",
    model=Port,
    description="Physical and logical ports. Used counts are derived from status and connections.",
    queryset=lambda: Port.objects.select_related("device").prefetch_related(
        "connections_a__port_b__device", "connections_b__port_a__device"
    ),
    search_fields=["label", "device__name", "provider", "circuit_id", "tagged_vlans"],
    default_sort="device__name",
    paste_fields=[
        "device",
        "label",
        "port_type",
        "speed",
        "poe",
        "access_vlan",
        "tagged_vlans",
        "status",
    ],
    form_fields=[
        "device",
        "label",
        "port_type",
        "speed",
        "poe",
        "access_vlan",
        "tagged_vlans",
        "connector",
        "fibre_type",
        "provider",
        "circuit_id",
        "status",
    ],
    filters=[
        Filter("status", "Status", "status", list(Port.Status.choices)),
        Filter("type", "Port type", "port_type", list(Port.Type.choices)),
        Filter("device", "Device", "device_id", []),
    ],
    columns=[
        Column("device", "Device", "device", kind="fk", editable=True),
        Column("label", "Label", "label", editable=True, mono=True),
        Column("type", "Type", "port_type", kind="choice", editable=True, badge=True),
        Column("speed", "Speed", "speed", editable=True),
        Column("poe", "PoE", "poe", kind="bool", editable=True, width="60px"),
        Column("access_vlan", "VLAN", "access_vlan", editable=True, mono=True),
        Column("tagged", "Tagged", "tagged_vlans", editable=True),
        Column("status", "Status", "status", kind="choice", editable=True, badge=True),
        Column("connected", "Connected to", compute=_connected_to, sortable=False),
    ],
    empty_title="No ports punched in",
    empty_body="Add ports one at a time or paste a list such as 1-24.",
)

CONNECTION_CONFIG = TableConfig(
    kind="connections",
    title="Connections",
    singular="connection",
    model=Connection,
    description="Cables as recorded. An empty far end is an honest Unknown, not an error.",
    queryset=lambda: Connection.objects.select_related(
        "port_a__device", "port_b__device"
    ),
    search_fields=[
        "cable_label",
        "notes",
        "port_a__label",
        "port_a__device__name",
        "port_b__label",
        "port_b__device__name",
    ],
    default_sort="port_a__device__name",
    paste_fields=["port_a", "port_b", "cable_label", "notes"],
    form_fields=["port_a", "port_b", "cable_label", "notes", "source"],
    filters=[],
    columns=[
        Column("port_a", "Port A", compute=_connection_a, editable=False),
        Column("port_b", "Port B", compute=_connection_b, editable=False),
        Column("cable", "Cable label", "cable_label", editable=True, mono=True),
        Column("notes", "Notes", "notes", editable=True),
        Column("source", "Source", "source", kind="choice", badge=True),
        Column("updated", "Updated", "updated_at", kind="date", sortable=True),
    ],
    empty_title="No lines on this map yet",
    empty_body="Record a cable between two ports, or leave the far end Unknown.",
)

CONFIGS = {
    "devices": DEVICE_CONFIG,
    "ips": IP_CONFIG,
    "ports": PORT_CONFIG,
    "connections": CONNECTION_CONFIG,
}


def build_filters(config, request):
    filters = []
    for spec in config.filters:
        choices = spec.choices(request) if callable(spec.choices) else spec.choices
        current = request.GET.get(spec.param, "")
        filters.append(
            {
                "param": spec.param,
                "label": spec.label,
                "choices": choices,
                "current": current,
                "all_label": f"All {spec.label.lower()}",
            }
        )
    return filters


def _fk_filter_choices(model, label_field="__str__"):
    return [(str(obj.pk), str(obj)) for obj in model.objects.all()[:500]]


def filter_choices_for(config, request):
    for spec in config.filters:
        if spec.param == "subnet":
            spec.choices = [(str(s.pk), f"{s.cidr} · {s.name}") for s in Subnet.objects.all()]
        elif spec.param == "device":
            spec.choices = [(str(d.pk), d.name) for d in Device.objects.all()[:500]]
        elif spec.param == "site":
            sites = (
                Device.objects.exclude(location__site="")
                .values_list("location__site", flat=True)
                .distinct()
                .order_by("location__site")
            )
            spec.choices = [(site, site) for site in sites]
    return build_filters(config, request)


def filtered_queryset(config, request):
    qs = config.queryset()
    search = request.GET.get("q", "").strip()
    if search:
        query = Q()
        for field_name in config.search_fields:
            query |= Q(**{f"{field_name}__icontains": search})
        qs = qs.filter(query)

    for spec in config.filters:
        value = request.GET.get(spec.param, "").strip()
        if value:
            qs = qs.filter(**{spec.lookup: value})

    sort = request.GET.get("sort") or config.default_sort
    direction = request.GET.get("dir") or config.default_dir
    allowed = {col.key: (col.field or col.key) for col in config.columns if col.sortable}
    sort_field = allowed.get(sort, config.default_sort)
    if direction not in {"asc", "desc"}:
        direction = "asc"
    prefix = "-" if direction == "desc" else ""
    try:
        qs = qs.order_by(f"{prefix}{sort_field}", "pk")
    except Exception:
        qs = qs.order_by(config.default_sort)
    return qs


def cell_context(config, obj, column):
    return {
        "col": column,
        "value": _format_value(obj, column),
        "editable": column.editable and bool(column.field),
        "edit_url": reverse("table_cell", args=[config.kind, obj.pk, column.field])
        if column.editable and column.field
        else "",
        "badge_class": BADGE_CLASSES.get(getattr(obj, column.field, ""), "")
        if column.badge and column.field
        else "",
    }


def build_table(config, request):
    qs = filtered_queryset(config, request)
    paginator = Paginator(qs, 60)
    page = paginator.get_page(request.GET.get("page"))

    rows = []
    for obj in page.object_list:
        rows.append(
            {
                "obj": obj,
                "cells": [cell_context(config, obj, col) for col in config.columns],
            }
        )

    current_sort = request.GET.get("sort") or config.default_sort
    current_dir = request.GET.get("dir") or config.default_dir
    sort_meta = {}
    for col in config.columns:
        params = request.GET.copy()
        params["sort"] = col.key
        params["dir"] = (
            "desc" if current_sort == col.key and current_dir == "asc" else "asc"
        )
        params.pop("page", None)
        arrow = ""
        if current_sort == col.key:
            arrow = "↑" if current_dir == "asc" else "↓"
        sort_meta[col.key] = {"url": f"?{params.urlencode()}", "arrow": arrow}

    return {
        "config": config,
        "rows": rows,
        "page": page,
        "total": paginator.count,
        "filters": filter_choices_for(config, request),
        "search": request.GET.get("q", ""),
        "query_string": request.GET.urlencode(),
        "current_sort": current_sort,
        "current_dir": current_dir,
        "sort_meta": sort_meta,
        "has_filters": any(
            request.GET.get(spec.param) for spec in config.filters
        ) or bool(request.GET.get("q")),
    }

"""Build the topology graph used by the map view."""
from __future__ import annotations

from django.db.models import Q
from django.urls import reverse

from ..models import Connection, Device, Location, Port


LAYOUTS = [
    ("saved", "Saved positions"),
    ("cose", "Organic"),
    ("breadthfirst", "Branches"),
    ("circle", "Ring"),
    ("concentric", "Rings by degree"),
    ("grid", "Grid"),
]


def _device_href(device):
    return reverse("device_detail", args=[device.pk])


def topology_context(request):
    site = request.GET.get("site", "").strip()
    device_type = request.GET.get("type", "").strip()
    status = request.GET.get("status", "").strip()
    search = request.GET.get("q", "").strip()
    outage_only = request.GET.get("outage", "0") == "1"
    include_isolated = request.GET.get("isolated", "1") == "1"
    show_unknown = request.GET.get("unknown", "1") == "1"
    requested_layout = request.GET.get("layout", "").strip()

    devices = Device.objects.select_related("location").prefetch_related("ports", "outages")
    if site:
        devices = devices.filter(location__site=site)
    if device_type:
        devices = devices.filter(device_type=device_type)
    if status:
        devices = devices.filter(status=status)
    if search:
        devices = devices.filter(
            Q(name__icontains=search)
            | Q(vendor__icontains=search)
            | Q(model__icontains=search)
            | Q(serial_number__icontains=search)
            | Q(hostname__icontains=search)
            | Q(management_ip__icontains=search)
        )

    all_devices = list(devices.order_by("name"))
    all_connections = list(
        Connection.objects.select_related(
            "port_a__device", "port_b__device"
        ).order_by("pk")
    )
    connected_device_ids = set()
    connected_port_ids = set()
    for connection in all_connections:
        connected_device_ids.add(connection.port_a.device_id)
        connected_port_ids.add(connection.port_a_id)
        if connection.port_b_id:
            connected_device_ids.add(connection.port_b.device_id)
            connected_port_ids.add(connection.port_b_id)

    open_outage_ids = {
        device.pk
        for device in Device.objects.filter(outages__ended__isnull=True).distinct()
    }

    if outage_only:
        wanted = [device for device in all_devices if device.pk in open_outage_ids]
    else:
        wanted = all_devices
    if not include_isolated:
        wanted = [device for device in wanted if device.pk in connected_device_ids]

    visible_ids = {device.pk for device in wanted}
    nodes = []
    for device in wanted:
        ports = list(device.ports.all())
        used_ports = sum(
            1
            for port in ports
            if port.pk in connected_port_ids
            or port.status in {Port.Status.UP, Port.Status.IN_USE}
        )
        open_outages = [outage for outage in device.outages.all() if outage.ended is None]
        nodes.append(
            {
                "id": str(device.pk),
                "kind": "device",
                "label": device.name,
                "name": device.name,
                "type": device.device_type,
                "type_label": device.get_device_type_display(),
                "status": device.status,
                "status_label": device.get_status_display(),
                "site": device.location.site if device.location else "",
                "location": str(device.location) if device.location else "Unplaced",
                "management_ip": device.management_ip or "",
                "hostname": device.hostname,
                "vendor": device.vendor,
                "model": device.model,
                "serial": device.serial_number or "",
                "ports_used": used_ports,
                "ports_total": len(ports),
                "outage": bool(open_outages),
                "outage_cause": open_outages[0].cause if open_outages else "",
                "needs_identifying": device.needs_identifying,
                "source": device.get_source_display(),
                "url": _device_href(device),
                "x": device.graph_x,
                "y": device.graph_y,
            }
        )

    edges = []
    unknown_nodes = []
    for connection in all_connections:
        a_visible = connection.port_a.device_id in visible_ids
        b_visible = (
            connection.port_b_id is not None
            and connection.port_b.device_id in visible_ids
        )
        if connection.port_b_id is None:
            if not a_visible or not show_unknown:
                continue
            unknown_id = f"unknown-{connection.pk}"
            unknown_nodes.append(
                {
                    "id": unknown_id,
                    "kind": "unknown",
                    "label": "Unknown far end",
                    "name": "Unknown far end",
                    "detail": f"{connection.port_a.device.name}:{connection.port_a.label}",
                }
            )
            edges.append(
                {
                    "id": f"connection-{connection.pk}",
                    "source": str(connection.port_a.device_id),
                    "target": unknown_id,
                    "label": connection.cable_label or "unknown",
                    "cable": connection.cable_label,
                    "unknown": True,
                    "outage": connection.port_a.device_id in open_outage_ids,
                    "a": f"{connection.port_a.device.name}:{connection.port_a.label}",
                    "b": "Unknown",
                }
            )
            continue
        if not (a_visible and b_visible):
            continue
        edges.append(
            {
                "id": f"connection-{connection.pk}",
                "source": str(connection.port_a.device_id),
                "target": str(connection.port_b.device_id),
                "label": connection.cable_label or "",
                "cable": connection.cable_label,
                "unknown": False,
                "outage": (
                    connection.port_a.device_id in open_outage_ids
                    or connection.port_b.device_id in open_outage_ids
                ),
                "a": f"{connection.port_a.device.name}:{connection.port_a.label}",
                "b": f"{connection.port_b.device.name}:{connection.port_b.label}",
            }
        )

    device_nodes = nodes
    saved_count = sum(1 for node in device_nodes if node["x"] is not None and node["y"] is not None)
    if requested_layout in {key for key, _ in LAYOUTS}:
        layout = requested_layout
    elif device_nodes and saved_count == len(device_nodes):
        layout = "saved"
    else:
        layout = "cose"

    sites = (
        Location.objects.exclude(site="")
        .values_list("site", flat=True)
        .distinct()
        .order_by("site")
    )
    graph = {
        "nodes": nodes + unknown_nodes,
        "edges": edges,
        "layout": layout,
        "saveUrl": reverse("topology_layout"),
        "exportName": "netmap-topology.png",
        "savedCount": saved_count,
        "deviceCount": len(device_nodes),
        "stats": {
            "nodes": len(device_nodes),
            "edges": len(edges),
            "unknown": len(unknown_nodes),
            "outages": sum(1 for node in device_nodes if node["outage"]),
        },
    }
    return {
        "graph": graph,
        "sites": sites,
        "types": Device.Type.choices,
        "statuses": Device.Status.choices,
        "layouts": LAYOUTS,
        "selected": {
            "site": site,
            "type": device_type,
            "status": status,
            "q": search,
            "outage": outage_only,
            "isolated": include_isolated,
            "unknown": show_unknown,
            "layout": layout,
        },
        "all_device_count": Device.objects.count(),
        "all_connection_count": Connection.objects.count(),
        "visible_count": len(device_nodes),
        "edge_count": len(edges),
        "unknown_count": len(unknown_nodes),
        "outage_count": graph["stats"]["outages"],
    }

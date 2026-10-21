from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from ..forms import DeviceForm
from ..models import ChangeLog, Connection, Device
from ..services.racks import build_rack_view


@login_required
@require_GET
def device_detail(request, pk):
    device = get_object_or_404(
        Device.objects.select_related("location").prefetch_related("outages"), pk=pk
    )
    ports = list(device.ports.all())
    connections = list(
        Connection.objects.filter(Q(port_a__device=device) | Q(port_b__device=device))
        .select_related("port_a__device", "port_b__device")
        .order_by("port_a_id", "pk")
    )
    by_port = defaultdict(list)
    for connection in connections:
        by_port[connection.port_a_id].append(connection)
        if connection.port_b_id:
            by_port[connection.port_b_id].append(connection)

    port_rows = []
    used_ports = 0
    for port in ports:
        port_connections = []
        for connection in by_port[port.pk]:
            other = (
                connection.port_b
                if connection.port_a_id == port.pk
                else connection.port_a
            )
            port_connections.append(
                {
                    "connection": connection,
                    "other": f"{other.device.name}:{other.label}" if other else "Unknown",
                    "unknown": other is None,
                }
            )
        used = port.status in {"up", "in_use"} or bool(port_connections)
        if used:
            used_ports += 1
        port_rows.append({"port": port, "connections": port_connections, "used": used})

    ip_addresses = list(
        device.ip_addresses.select_related("subnet").order_by("subnet__cidr", "address")
    )
    outages = list(device.outages.order_by("-started"))
    open_outage = next((outage for outage in outages if outage.ended is None), None)
    changes = list(
        ChangeLog.objects.filter(object_type="Device", object_id=str(device.pk))
        .select_related("user")
        .order_by("-timestamp", "-pk")[:40]
    )
    for entry in changes:
        entry.field_label = entry.field.replace("_", " ") if entry.field else ""

    return render(
        request,
        "inventory/device_detail.html",
        {
            "device": device,
            "port_rows": port_rows,
            "port_count": len(ports),
            "used_ports": used_ports,
            "ip_addresses": ip_addresses,
            "connections": connections,
            "outages": outages,
            "open_outage": open_outage,
            "changes": changes,
            "change_count": ChangeLog.objects.filter(
                object_type="Device", object_id=str(device.pk)
            ).count(),
        },
    )


@login_required
def device_edit(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if request.method == "POST":
        form = DeviceForm(request.POST, instance=device)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated {device.name}.")
            return redirect("device_detail", pk=device.pk)
    else:
        form = DeviceForm(instance=device)
    return render(
        request,
        "inventory/device_form.html",
        {"form": form, "device": device, "form_title": f"Edit {device.name}"},
    )


@login_required
@require_POST
def device_verify(request, pk):
    device = get_object_or_404(Device, pk=pk)
    device.last_verified = timezone.localdate()
    device.save(update_fields=["last_verified"])
    messages.success(request, f"Marked {device.name} verified today.")
    return redirect("device_detail", pk=device.pk)


@login_required
@require_GET
def rack_view(request):
    return render(
        request,
        "inventory/rack_view.html",
        build_rack_view(request.GET.get("site", "").strip()),
    )

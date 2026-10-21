import json
import math

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from ..models import Device
from ..services.topology import topology_context


@login_required
@require_GET
def dashboard(request):
    return render(request, "inventory/topology.html", topology_context(request))


@login_required
@require_POST
def topology_layout(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid layout payload."}, status=400)
    positions = payload.get("positions")
    if not isinstance(positions, dict) or not positions:
        return JsonResponse({"ok": False, "error": "No positions supplied."}, status=400)
    if len(positions) > 10000:
        return JsonResponse({"ok": False, "error": "Too many positions."}, status=400)

    updates = []
    for raw_pk, position in positions.items():
        if not str(raw_pk).isdigit() or not isinstance(position, dict):
            return JsonResponse({"ok": False, "error": "Invalid device position."}, status=400)
        try:
            x = float(position.get("x"))
            y = float(position.get("y"))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Positions must be numbers."}, status=400)
        if not math.isfinite(x) or not math.isfinite(y):
            return JsonResponse({"ok": False, "error": "Positions must be finite."}, status=400)
        if abs(x) > 1_000_000 or abs(y) > 1_000_000:
            return JsonResponse({"ok": False, "error": "Position is out of range."}, status=400)
        updates.append((int(raw_pk), round(x, 2), round(y, 2)))

    devices = {device.pk: device for device in Device.objects.filter(pk__in=[item[0] for item in updates])}
    missing = [pk for pk in (item[0] for item in updates) if pk not in devices]
    if missing:
        return JsonResponse(
            {"ok": False, "error": f"Device {missing[0]} no longer exists."},
            status=404,
        )
    changed = []
    for pk, x, y in updates:
        device = devices[pk]
        device.graph_x = x
        device.graph_y = y
        changed.append(device)
    Device.objects.bulk_update(changed, ["graph_x", "graph_y"])
    return JsonResponse({"ok": True, "saved": len(changed)})

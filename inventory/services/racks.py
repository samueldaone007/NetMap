"""Rack elevation data."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Prefetch

from ..models import Device, Location


@dataclass
class Rack:
    location: Location
    height: int
    rows: list
    unpositioned: list
    device_count: int
    used_units: int
    conflicts: list = field(default_factory=list)


def _rack_for(location, devices):
    positioned = [device for device in devices if device.rack_unit]
    by_unit = defaultdict(list)
    for device in positioned:
        by_unit[device.rack_unit].append(device)
    max_unit = max((device.rack_unit for device in positioned), default=0)
    height = max(42, max_unit)
    rows = [
        {
            "unit": unit,
            "devices": by_unit.get(unit, []),
            "conflict": len(by_unit.get(unit, [])) > 1,
        }
        for unit in range(height, 0, -1)
    ]
    conflicts = [
        {"unit": unit, "devices": entries}
        for unit, entries in sorted(by_unit.items(), reverse=True)
        if len(entries) > 1
    ]
    return Rack(
        location=location,
        height=height,
        rows=rows,
        unpositioned=[device for device in devices if not device.rack_unit],
        device_count=len(devices),
        used_units=len(by_unit),
        conflicts=conflicts,
    )


def build_rack_view(site: str = ""):
    locations = (
        Location.objects.prefetch_related(
            Prefetch(
                "devices",
                queryset=Device.objects.select_related("location")
                .prefetch_related("outages")
                .order_by("name"),
            )
        )
        .order_by("site", "building", "room", "rack", "pk")
    )
    if site:
        locations = locations.filter(site=site)

    groups = {}
    for location in locations:
        devices = list(location.devices.all())
        if not devices:
            continue
        key = (
            location.site.casefold(),
            location.building.casefold(),
            location.room.casefold(),
            location.rack.casefold(),
        )
        if key not in groups:
            groups[key] = {"location": location, "devices": []}
        groups[key]["devices"].extend(devices)

    racks = [
        _rack_for(group["location"], sorted(group["devices"], key=lambda item: item.name))
        for _, group in sorted(groups.items())
    ]

    unplaced = []
    if not site:
        unplaced = list(
            Device.objects.filter(location__isnull=True)
            .prefetch_related("outages")
            .order_by("name")
        )
    sites = (
        Location.objects.exclude(site="")
        .values_list("site", flat=True)
        .distinct()
        .order_by("site")
    )
    return {
        "racks": racks,
        "sites": sites,
        "site": site,
        "rack_count": len(racks),
        "device_count": sum(rack.device_count for rack in racks) + len(unplaced),
        "unplaced": unplaced,
    }

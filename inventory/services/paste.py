"""Bulk paste-in of tab-separated spreadsheet rows."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from ..models import Connection, Device, IPAddress, Location, Port, Subnet
from .naming import next_placeholder_name
from .ports import expand_port_labels

EMPTY_VALUES = {"", "nil", "n/a", "na", "-", "none", "null"}
YES_VALUES = {"1", "y", "yes", "true", "poe", "on"}


class PasteError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class PasteResult:
    created: int
    details: list[str] = field(default_factory=list)
    kind: str = ""


def clean_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = str(value).replace("\u00a0", " ").strip()
    if text.lower() in EMPTY_VALUES:
        return ""
    return text


def parse_rows(text: str) -> list[list[str]]:
    lines = [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    rows = []
    for line in lines:
        if not line.strip():
            continue
        delimiter = "\t" if "\t" in line else ","
        rows.append([clean_cell(cell) for cell in line.split(delimiter)])
    return rows


def _normalise_label(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _looks_like_header(row: list[str], fields: list[str]) -> bool:
    aliases = set(fields) | {field.replace("_", " ") for field in fields}
    aliases |= {"name", "device name", "port a", "port b", "ip", "cidr", "label"}
    cleaned = {_normalise_label(value) for value in row if value}
    return bool(cleaned) and cleaned.issubset({_normalise_label(alias) for alias in aliases})


def _choice(model, field_name: str, raw: str):
    raw = clean_cell(raw)
    if not raw:
        return None
    choices = dict(model._meta.get_field(field_name).choices or [])
    for value, label in choices.items():
        if raw.lower() in {str(value).lower(), str(label).lower()}:
            return value
    raise ValueError(f"{raw!r} is not a valid {field_name.replace('_', ' ')}.")


def _resolve_device(raw: str, required: bool = True):
    raw = clean_cell(raw)
    if not raw:
        if required:
            raise ValueError("A device name is required.")
        return None
    if raw.isdigit():
        found = Device.objects.filter(pk=int(raw)).first()
        if found:
            return found
    found = Device.objects.filter(name__iexact=raw).first()
    if found:
        return found
    raise ValueError(f"Device {raw!r} was not found. Add it first.")


def _resolve_subnet(raw: str):
    raw = clean_cell(raw)
    if not raw:
        raise ValueError("A subnet is required (CIDR or name).")
    found = (
        Subnet.objects.filter(cidr__iexact=raw).first()
        or Subnet.objects.filter(name__iexact=raw).first()
    )
    if not found and raw.isdigit():
        found = Subnet.objects.filter(pk=int(raw)).first()
    if not found:
        raise ValueError(f"Subnet {raw!r} was not found.")
    return found


def _resolve_location(raw: str):
    raw = clean_cell(raw)
    if not raw:
        return None
    if raw.isdigit():
        found = Location.objects.filter(pk=int(raw)).first()
        if found:
            return found
    matches = [loc for loc in Location.objects.all() if str(loc).lower() == raw.lower()]
    if matches:
        return matches[0]
    raise ValueError(f"Location {raw!r} was not found. Add the location first.")


def _resolve_port(raw: str, required: bool = True):
    raw = clean_cell(raw)
    if not raw:
        if required:
            raise ValueError("Port A is required, for example core-sw-01:Gi0/1.")
        return None
    if ":" not in raw:
        raise ValueError(f"Port {raw!r} must look like device:label.")
    device_name, label = raw.rsplit(":", 1)
    device = Device.objects.filter(name__iexact=device_name.strip()).first()
    if not device:
        raise ValueError(f"Device {device_name.strip()!r} was not found for port {raw!r}.")
    port = Port.objects.filter(device=device, label__iexact=label.strip()).first()
    if not port:
        raise ValueError(f"Port {label.strip()!r} was not found on {device.name}.")
    return port


def _validate(obj, row_number: int, errors: list[str]):
    try:
        obj.full_clean()
    except ValidationError as exc:
        for field, messages in exc.message_dict.items():
            for message in messages:
                errors.append(f"Row {row_number}, {field}: {message}")


def _paste_devices(rows: list[list[str]], fields: list[str]) -> PasteResult:
    objects: list[Device] = []
    errors: list[str] = []
    used_names: set[str] = set()
    for offset, row in enumerate(rows, start=1):
        data = dict(zip(fields, row + [""] * (len(fields) - len(row))))
        try:
            name = clean_cell(data.get("name"))
            if not name:
                name = next_placeholder_name()
                while name.lower() in used_names:
                    number = int(name.rsplit("-", 1)[1]) + 1
                    name = f"UNNAMED-{number:03d}"
            used_names.add(name.lower())
            device_type = _choice(Device, "device_type", data.get("device_type") or "other")
            status = _choice(Device, "status", data.get("status") or "active")
            device = Device(
                name=name,
                device_type=device_type,
                vendor=clean_cell(data.get("vendor")),
                model=clean_cell(data.get("model")),
                serial_number=clean_cell(data.get("serial_number")) or None,
                asset_id=clean_cell(data.get("asset_id")) or None,
                management_ip=clean_cell(data.get("management_ip")) or None,
                owner=clean_cell(data.get("owner")),
                status=status,
                location=_resolve_location(data.get("location")),
                needs_identifying=not clean_cell(data.get("name")),
                source=Device._meta.get_field("source").default,
            )
            _validate(device, offset, errors)
            if device.name.lower() in {obj.name.lower() for obj in objects}:
                errors.append(f"Row {offset}: device {device.name!r} appears twice in this paste.")
            objects.append(device)
        except (ValueError, ValidationError) as exc:
            errors.append(f"Row {offset}: {exc}")
    if errors:
        raise PasteError(errors)
    with transaction.atomic():
        for obj in objects:
            obj.save()
    return PasteResult(len(objects), [f"{obj.name}" for obj in objects], "devices")


def _paste_ips(rows: list[list[str]], fields: list[str]) -> PasteResult:
    objects: list[IPAddress] = []
    errors: list[str] = []
    seen: set[str] = set()
    for offset, row in enumerate(rows, start=1):
        data = dict(zip(fields, row + [""] * (len(fields) - len(row))))
        try:
            subnet = _resolve_subnet(data.get("subnet"))
            address = clean_cell(data.get("address"))
            status = _choice(IPAddress, "status", data.get("status") or "used")
            ip = IPAddress(
                address=address,
                subnet=subnet,
                device=_resolve_device(data.get("device"), required=False),
                hostname=clean_cell(data.get("hostname")),
                status=status,
            )
            _validate(ip, offset, errors)
            if ip.address in seen:
                errors.append(f"Row {offset}: {ip.address} appears twice in this paste.")
            seen.add(ip.address)
            objects.append(ip)
        except (ValueError, ValidationError) as exc:
            errors.append(f"Row {offset}: {exc}")
    if errors:
        raise PasteError(errors)
    with transaction.atomic():
        for obj in objects:
            obj.save()
    return PasteResult(len(objects), [f"{obj.address}" for obj in objects], "ips")


def _paste_ports(rows: list[list[str]], fields: list[str]) -> PasteResult:
    objects: list[Port] = []
    errors: list[str] = []
    seen: set[tuple[int, str]] = set()
    for offset, row in enumerate(rows, start=1):
        data = dict(zip(fields, row + [""] * (len(fields) - len(row))))
        try:
            device = _resolve_device(data.get("device"))
            labels = expand_port_labels(data.get("label"))
            if not labels:
                raise ValueError("A port label is required.")
            port_type = _choice(Port, "port_type", data.get("port_type") or "ethernet")
            status = _choice(Port, "status", data.get("status") or "unknown")
            for label in labels:
                access_vlan = clean_cell(data.get("access_vlan"))
                port = Port(
                    device=device,
                    label=label,
                    port_type=port_type,
                    speed=clean_cell(data.get("speed")),
                    poe=clean_cell(data.get("poe")).lower() in YES_VALUES,
                    access_vlan=int(access_vlan) if access_vlan else None,
                    tagged_vlans=clean_cell(data.get("tagged_vlans")),
                    status=status,
                )
                _validate(port, offset, errors)
                key = (device.pk, label.lower())
                if key in seen:
                    errors.append(
                        f"Row {offset}: {device.name}:{label} appears twice after expansion."
                    )
                seen.add(key)
                objects.append(port)
        except (ValueError, ValidationError) as exc:
            errors.append(f"Row {offset}: {exc}")
    if errors:
        raise PasteError(errors)
    with transaction.atomic():
        for obj in objects:
            obj.save()
    return PasteResult(len(objects), [f"{obj.device.name}:{obj.label}" for obj in objects], "ports")


def _paste_connections(rows: list[list[str]], fields: list[str]) -> PasteResult:
    objects: list[Connection] = []
    errors: list[str] = []
    seen: set[tuple[int, int | None]] = set()
    for offset, row in enumerate(rows, start=1):
        data = dict(zip(fields, row + [""] * (len(fields) - len(row))))
        try:
            port_a = _resolve_port(data.get("port_a"))
            port_b = _resolve_port(data.get("port_b"), required=False)
            connection = Connection(
                port_a=port_a,
                port_b=port_b,
                cable_label=clean_cell(data.get("cable_label")),
                notes=clean_cell(data.get("notes")),
            )
            _validate(connection, offset, errors)
            key = (port_a.pk, port_b.pk if port_b else None)
            reverse = (port_b.pk, port_a.pk) if port_b else None
            if key in seen or (reverse and reverse in seen):
                errors.append(f"Row {offset}: this cable appears twice in the paste.")
            seen.add(key)
            objects.append(connection)
        except (ValueError, ValidationError) as exc:
            errors.append(f"Row {offset}: {exc}")
    if errors:
        raise PasteError(errors)
    with transaction.atomic():
        for obj in objects:
            obj.save()
    return PasteResult(len(objects), [str(obj) for obj in objects], "connections")


PASTERS = {
    "devices": _paste_devices,
    "ips": _paste_ips,
    "ports": _paste_ports,
    "connections": _paste_connections,
}


def paste_rows(kind: str, text: str, fields: list[str]) -> PasteResult:
    rows = parse_rows(text)
    if not rows:
        raise PasteError(["Nothing to paste. Include at least one row."])
    if fields and len(rows[0]) > len(fields):
        raise PasteError(
            [f"This table accepts {len(fields)} columns ({', '.join(fields)}), but the first row has {len(rows[0])}."]
        )
    if rows and _looks_like_header(rows[0], fields):
        rows = rows[1:]
    if not rows:
        raise PasteError(["Only a header row was pasted. Add at least one data row."])
    return PASTERS[kind](rows, fields)

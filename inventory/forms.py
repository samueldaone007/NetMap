"""Forms used by table CRUD, inline editing and imports."""
from __future__ import annotations

from functools import lru_cache

from django import forms
from django.forms import modelform_factory

from .models import Connection, Device, IPAddress, Location, Outage, Port, Subnet
from .tables import CONFIGS


LABELS = {
    "device_type": "Device type",
    "port_type": "Port type",
    "os_version": "OS / version",
    "management_ip": "Management IP",
    "asset_id": "Asset ID",
    "serial_number": "Serial number",
    "warranty_expiry": "Warranty expiry",
    "purchase_date": "Purchase date",
    "last_verified": "Last verified",
    "needs_identifying": "Needs identifying",
    "source": "Source",
    "port_a": "Port A",
    "port_b": "Port B (leave empty if Unknown)",
    "cable_label": "Cable label",
    "access_vlan": "Access VLAN",
    "tagged_vlans": "Tagged VLANs",
    "fibre_type": "Fibre type",
    "circuit_id": "Provider / circuit ID",
    "rack_unit": "Rack unit (U)",
    "vlan_id": "VLAN ID",
    "ip": "IP address",
    "cidr": "CIDR",
    "device": "Device (choose one)",
    "connection": "Connection (choose one)",
    "cause": "Cause",
    "started": "Started",
    "ended": "Ended (leave blank while open)",
}

HELP_TEXT = {
    "needs_identifying": "Flag this record for a later site walk.",
    "port_b": "Leave empty to record an Unknown far end.",
    "rack_unit": "Optional. Devices without a U position still appear in the rack tray.",
    "tagged_vlans": "Comma-separated, e.g. 10,20,30.",
    "source": "Manual, imported, or reserved for future discovery.",
    "connection": "Pick a cable if the outage affects a link rather than a single device.",
    "ended": "Leave empty while the outage is still open. Closing it stamps the time.",
}


class NetMapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.label = LABELS.get(name, field.label)
            if name in HELP_TEXT:
                field.help_text = HELP_TEXT[name]
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
            if isinstance(field, forms.DateTimeField):
                field.widget = forms.DateTimeInput(
                    attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
                )


@lru_cache(maxsize=None)
def form_class_for(kind: str, fields: tuple[str, ...] | None = None):
    config = CONFIGS[kind]
    selected = list(fields) if fields else config.form_fields
    return modelform_factory(
        config.model,
        form=NetMapModelForm,
        fields=selected,
    )


@lru_cache(maxsize=None)
def inline_form_class(model, field_name: str):
    return modelform_factory(
        model,
        form=NetMapModelForm,
        fields=[field_name],
    )


class SubnetForm(NetMapModelForm):
    class Meta:
        model = Subnet
        fields = ["cidr", "vlan_id", "name", "gateway", "purpose"]


class LocationForm(NetMapModelForm):
    class Meta:
        model = Location
        fields = ["site", "building", "room", "rack", "rack_unit", "notes"]


class ConnectionForm(NetMapModelForm):
    class Meta:
        model = Connection
        fields = ["port_a", "port_b", "cable_label", "notes", "source"]


class DeviceForm(NetMapModelForm):
    class Meta:
        model = Device
        fields = CONFIGS["devices"].form_fields


class IPAddressForm(NetMapModelForm):
    class Meta:
        model = IPAddress
        fields = CONFIGS["ips"].form_fields


class PortForm(NetMapModelForm):
    class Meta:
        model = Port
        fields = CONFIGS["ports"].form_fields


class OutageForm(NetMapModelForm):
    class Meta:
        model = Outage
        fields = ["device", "connection", "started", "ended", "cause", "notes"]

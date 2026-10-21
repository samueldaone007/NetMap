import ipaddress

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse


class Source(models.TextChoices):
    MANUAL = "manual", "Manual"
    IMPORT = "import", "Import"
    DISCOVERY = "discovery", "Future discovery"


class Location(models.Model):
    site = models.CharField(max_length=120)
    building = models.CharField(max_length=120, blank=True)
    room = models.CharField(max_length=120, blank=True)
    rack = models.CharField(max_length=120, blank=True)
    rack_unit = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        help_text="Optional U position. Leave blank if the unit is not known yet.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["site", "building", "room", "rack", "rack_unit", "pk"]

    def __str__(self):
        parts = [self.site, self.building, self.room, self.rack]
        label = " · ".join(part for part in parts if part)
        if self.rack_unit:
            label = f"{label} · U{self.rack_unit}"
        return label or "Unplaced location"

    @property
    def rack_path(self):
        parts = [self.site, self.building, self.room, self.rack]
        return " · ".join(part for part in parts if part) or "Unplaced rack"

    @property
    def short_label(self):
        return self.rack_path


class Subnet(models.Model):
    cidr = models.CharField(max_length=43, unique=True)
    vlan_id = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(4094)],
    )
    name = models.CharField(max_length=160)
    gateway = models.GenericIPAddressField(null=True, blank=True)
    purpose = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cidr"]

    def __str__(self):
        return f"{self.name} · {self.cidr}"

    def clean(self):
        super().clean()
        if not self.cidr:
            return
        try:
            network = ipaddress.ip_network(self.cidr.strip(), strict=False)
        except ValueError as exc:
            raise ValidationError({"cidr": f"Enter a valid CIDR, for example 192.168.10.0/24 ({exc})."})
        self.cidr = str(network)
        if self.gateway:
            try:
                gateway = ipaddress.ip_address(str(self.gateway).strip())
            except ValueError as exc:
                raise ValidationError({"gateway": f"Enter a valid gateway address ({exc})."}) from exc
            if gateway not in network:
                raise ValidationError({"gateway": "The gateway must sit inside this subnet."})
            self.gateway = str(gateway)

    def save(self, *args, **kwargs):
        if self.cidr:
            try:
                self.cidr = str(ipaddress.ip_network(self.cidr.strip(), strict=False))
            except ValueError:
                pass
        super().save(*args, **kwargs)

    @property
    def network(self):
        return ipaddress.ip_network(self.cidr, strict=False)

    @property
    def usable_hosts(self):
        if self.network.version != 4:
            return []
        return list(self.network.hosts())

    @property
    def host_count(self):
        if self.network.version == 4:
            return max(self.network.num_addresses - 2, 0)
        return self.network.num_addresses

    @property
    def used_count(self):
        return self.ips.filter(status=IPAddress.Status.USED).count()

    @property
    def free_count(self):
        return max(self.host_count - self.ips.exclude(status=IPAddress.Status.FREE).count(), 0)

    def get_absolute_url(self):
        return reverse("subnet_detail", args=[self.pk])


class Device(models.Model):
    class Type(models.TextChoices):
        SERVER = "server", "Server"
        SWITCH = "switch", "Switch"
        ROUTER = "router", "Router"
        FIREWALL = "firewall", "Firewall"
        AP = "ap", "Access point"
        PATCH_PANEL = "patch_panel", "Patch panel"
        EXTERNAL = "external", "External"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SPARE = "spare", "Spare"
        RETIRED = "retired", "Retired"

    name = models.CharField(max_length=200, unique=True)
    asset_id = models.CharField(max_length=120, unique=True, null=True, blank=True)
    device_type = models.CharField(max_length=30, choices=Type.choices, default=Type.OTHER)
    vendor = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=160, blank=True)
    serial_number = models.CharField(max_length=160, unique=True, null=True, blank=True)
    hostname = models.CharField(max_length=200, blank=True)
    os_version = models.CharField(max_length=200, blank=True, verbose_name="OS / version")
    firmware = models.CharField(max_length=200, blank=True)
    management_ip = models.GenericIPAddressField(null=True, blank=True)
    location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="devices"
    )
    rack_unit = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        help_text="Optional U position in the rack. Leave blank until it is read off the rail.",
    )
    owner = models.CharField(max_length=160, blank=True)
    purpose = models.TextField(blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    needs_identifying = models.BooleanField(
        default=False,
        help_text="Set for placeholder records that still need a human to name or verify them.",
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    last_verified = models.DateField(null=True, blank=True)
    import_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    graph_x = models.FloatField(null=True, blank=True)
    graph_y = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        for field in ("asset_id", "serial_number"):
            value = getattr(self, field)
            if isinstance(value, str):
                value = value.strip() or None
                setattr(self, field, value)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("device_detail", args=[self.pk])

    @property
    def display_model(self):
        return " ".join(part for part in (self.vendor, self.model) if part) or "—"

    def port_usage(self):
        ports = list(self.ports.all())
        used = sum(1 for port in ports if port.is_used)
        return used, len(ports)

    @property
    def ports_used(self):
        return self.port_usage()[0]

    @property
    def ports_total(self):
        return self.port_usage()[1]

    def has_open_outage(self):
        return any(outage.ended is None for outage in self.outages.all())

    has_open_outage.boolean = True
    has_open_outage.short_description = "Open outage"


class IPAddress(models.Model):
    class Status(models.TextChoices):
        USED = "used", "Used"
        FREE = "free", "Free"
        RESERVED = "reserved", "Reserved"

    address = models.GenericIPAddressField(unique=True)
    subnet = models.ForeignKey(Subnet, on_delete=models.CASCADE, related_name="ips")
    device = models.ForeignKey(
        Device, null=True, blank=True, on_delete=models.SET_NULL, related_name="ip_addresses"
    )
    hostname = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.USED)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    last_verified = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["address"]
        verbose_name = "IP address"
        verbose_name_plural = "IP addresses"

    def __str__(self):
        return self.address

    def clean(self):
        super().clean()
        if not self.address or not self.subnet_id:
            return
        try:
            address = ipaddress.ip_address(str(self.address).strip())
        except ValueError as exc:
            raise ValidationError({"address": f"Enter a valid IP address ({exc})."}) from exc
        try:
            network = ipaddress.ip_network(self.subnet.cidr, strict=False)
        except ValueError as exc:
            raise ValidationError({"subnet": "The selected subnet has an invalid CIDR."}) from exc
        if address not in network:
            raise ValidationError(
                {"address": f"{address} is outside {network}. Pick an address inside the subnet."}
            )
        if address.version == 4 and address in (network.network_address, network.broadcast_address):
            # Network and broadcast addresses are technically in the CIDR but not
            # assignable. Keep them out of the inventory table.
            if network.prefixlen < 31:
                raise ValidationError(
                    {"address": f"{address} is the network or broadcast address of {network}."}
                )
        self.address = str(address)

    def save(self, *args, **kwargs):
        if self.address:
            try:
                self.address = str(ipaddress.ip_address(str(self.address).strip()))
            except ValueError:
                pass
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("subnet_detail", args=[self.subnet_id])

    @property
    def is_usable(self):
        if self.subnet.network.version != 4:
            return True
        return self.address not in {
            str(self.subnet.network.network_address),
            str(self.subnet.network.broadcast_address),
        }


class Port(models.Model):
    class Type(models.TextChoices):
        ETHERNET = "ethernet", "Ethernet"
        FIBRE = "fibre", "Fibre"
        SFP = "sfp", "SFP"
        PATCH = "patch", "Patch"
        WAN = "wan", "WAN"

    class Status(models.TextChoices):
        UP = "up", "Up"
        DOWN = "down", "Down"
        FREE = "free", "Free"
        IN_USE = "in_use", "In use"
        UNKNOWN = "unknown", "Unknown"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="ports")
    label = models.CharField(max_length=120)
    port_type = models.CharField(max_length=20, choices=Type.choices, default=Type.ETHERNET)
    speed = models.CharField(max_length=40, blank=True)
    poe = models.BooleanField(default=False, verbose_name="PoE")
    access_vlan = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(4094)],
    )
    tagged_vlans = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated VLAN IDs."
    )
    connector = models.CharField(max_length=60, blank=True)
    fibre_type = models.CharField(max_length=60, blank=True)
    provider = models.CharField(max_length=120, blank=True)
    circuit_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNKNOWN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["device__name", "label"]
        constraints = [
            models.UniqueConstraint(fields=["device", "label"], name="unique_port_per_device")
        ]

    def __str__(self):
        return f"{self.device.name} · {self.label}"

    @property
    def is_connected(self):
        return bool(list(self.connections_a.all()) or list(self.connections_b.all()))

    @property
    def is_used(self):
        return self.status in {self.Status.UP, self.Status.IN_USE} or self.is_connected

    @property
    def connection_list(self):
        return list(self.connections_a.all()) + list(self.connections_b.all())

    @property
    def vlan_label(self):
        parts = []
        if self.access_vlan:
            parts.append(str(self.access_vlan))
        if self.tagged_vlans:
            parts.append(f"tagged {self.tagged_vlans}")
        return " / ".join(parts) or "—"


class Connection(models.Model):
    port_a = models.ForeignKey(
        Port, on_delete=models.PROTECT, related_name="connections_a"
    )
    port_b = models.ForeignKey(
        Port,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="connections_b",
        help_text="Leave as Unknown when the far end has not been traced yet.",
    )
    cable_label = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port_a__device__name", "port_a__label"]
        constraints = [
            models.UniqueConstraint(
                fields=["port_a", "port_b"],
                name="unique_connection_direction",
                condition=Q(port_b__isnull=False),
            )
        ]

    def __str__(self):
        other = self.port_b.label if self.port_b_id else "Unknown"
        return f"{self.port_a} ↔ {other}"

    def clean(self):
        super().clean()
        if self.port_b_id and self.port_a_id == self.port_b_id:
            raise ValidationError("A port cannot be connected to itself.")
        if not self.port_a_id:
            return
        duplicates = Connection.objects.filter(
            Q(port_a_id=self.port_a_id, port_b_id=self.port_b_id)
            | Q(port_a_id=self.port_b_id, port_b_id=self.port_a_id)
        ).exclude(pk=self.pk)
        if self.port_b_id and duplicates.exists():
            raise ValidationError("These two ports are already connected.")

    @property
    def is_unknown(self):
        return self.port_b_id is None


class ChangeLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Created"
        UPDATE = "update", "Updated"
        DELETE = "delete", "Deleted"

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    object_repr = models.CharField(max_length=240)
    action = models.CharField(max_length=12, choices=Action.choices, default=Action.UPDATE)
    field = models.CharField(max_length=120, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["-timestamp", "-pk"]
        verbose_name = "change log entry"
        verbose_name_plural = "change log"

    def __str__(self):
        return f"{self.object_type} {self.object_id}: {self.field}"


class Outage(models.Model):
    device = models.ForeignKey(
        Device, null=True, blank=True, on_delete=models.CASCADE, related_name="outages"
    )
    connection = models.ForeignKey(
        Connection,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="outages",
    )
    started = models.DateTimeField()
    ended = models.DateTimeField(null=True, blank=True)
    cause = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(device__isnull=False, connection__isnull=True)
                    | Q(device__isnull=True, connection__isnull=False)
                ),
                name="outage_has_one_subject",
            )
        ]

    def __str__(self):
        subject = self.device.name if self.device_id else str(self.connection)
        return f"{subject}: {self.cause}"

    def clean(self):
        super().clean()
        if bool(self.device_id) == bool(self.connection_id):
            raise ValidationError("Choose either a device or a connection for the outage.")
        if self.ended and self.started and self.ended < self.started:
            raise ValidationError({"ended": "The end time cannot be before the start time."})

    @property
    def is_open(self):
        return self.ended is None

    @property
    def duration(self):
        if not self.ended:
            return None
        return self.ended - self.started

    @property
    def subject(self):
        if self.device_id:
            return self.device
        return self.connection


class ImportBatch(models.Model):
    class Target(models.TextChoices):
        DEVICES = "devices", "Devices"
        PORTS = "ports", "Ports"
        CONNECTIONS = "connections", "Connections"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        MAPPED = "mapped", "Mapped"
        IMPORTED = "imported", "Imported"
        UNDONE = "undone", "Undone"
        ERROR = "error", "Error"

    uploaded_file = models.FileField(upload_to="imports/%Y/%m/")
    original_name = models.CharField(max_length=255)
    sheet_name = models.CharField(max_length=200, blank=True)
    has_header = models.BooleanField(default=True)
    target_type = models.CharField(max_length=20, choices=Target.choices, blank=True)
    mapping = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    summary = models.JSONField(default=dict, blank=True)
    undo_data = models.JSONField(default=dict, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

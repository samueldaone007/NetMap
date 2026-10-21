from django.contrib import admin

from .models import (
    ChangeLog,
    Connection,
    Device,
    ImportBatch,
    IPAddress,
    Location,
    Outage,
    Port,
    Subnet,
)


class PortInline(admin.TabularInline):
    model = Port
    extra = 0
    fields = ("label", "port_type", "speed", "poe", "access_vlan", "tagged_vlans", "status")


class IPInline(admin.TabularInline):
    model = IPAddress
    extra = 0
    fields = ("address", "hostname", "status", "source", "last_verified")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("site", "building", "room", "rack", "rack_unit")
    list_filter = ("site", "building", "room", "rack")
    search_fields = ("site", "building", "room", "rack", "notes")


@admin.register(Subnet)
class SubnetAdmin(admin.ModelAdmin):
    list_display = ("name", "cidr", "vlan_id", "gateway", "purpose")
    list_filter = ("vlan_id",)
    search_fields = ("name", "cidr", "gateway", "purpose")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "device_type",
        "vendor",
        "model",
        "location",
        "status",
        "needs_identifying",
        "source",
    )
    list_filter = ("device_type", "status", "source", "needs_identifying", "location__site")
    search_fields = (
        "name",
        "asset_id",
        "serial_number",
        "hostname",
        "management_ip",
        "vendor",
        "model",
    )
    autocomplete_fields = ("location",)
    inlines = [PortInline, IPInline]
    readonly_fields = ("created_at", "updated_at", "import_fingerprint")


@admin.register(IPAddress)
class IPAddressAdmin(admin.ModelAdmin):
    list_display = ("address", "subnet", "device", "hostname", "status", "source", "last_verified")
    list_filter = ("status", "source", "subnet")
    search_fields = ("address", "hostname", "device__name")
    autocomplete_fields = ("subnet", "device")


@admin.register(Port)
class PortAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "label",
        "port_type",
        "speed",
        "poe",
        "access_vlan",
        "tagged_vlans",
        "status",
    )
    list_filter = ("port_type", "status", "poe")
    search_fields = ("device__name", "label", "provider", "circuit_id", "tagged_vlans")
    autocomplete_fields = ("device",)


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ("port_a", "port_b", "cable_label", "source", "updated_at")
    search_fields = (
        "port_a__device__name",
        "port_a__label",
        "port_b__device__name",
        "port_b__label",
        "cable_label",
    )
    autocomplete_fields = ("port_a", "port_b")


@admin.register(Outage)
class OutageAdmin(admin.ModelAdmin):
    list_display = ("started", "device", "connection", "cause", "ended")
    list_filter = ("started",)
    search_fields = ("device__name", "cause", "notes")
    autocomplete_fields = ("device", "connection")


@admin.register(ChangeLog)
class ChangeLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "object_type", "object_repr", "action", "field", "user")
    list_filter = ("object_type", "action", "user")
    search_fields = ("object_repr", "field", "old_value", "new_value")
    readonly_fields = (
        "timestamp",
        "object_type",
        "object_id",
        "object_repr",
        "action",
        "field",
        "old_value",
        "new_value",
        "user",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("original_name", "sheet_name", "target_type", "status", "row_count", "created_at")
    list_filter = ("status", "target_type")
    search_fields = ("original_name", "sheet_name")
    readonly_fields = (
        "uploaded_file",
        "original_name",
        "sheet_name",
        "target_type",
        "mapping",
        "status",
        "summary",
        "undo_data",
        "row_count",
        "uploaded_by",
        "created_at",
        "updated_at",
        "imported_at",
        "undone_at",
    )


admin.site.site_header = "NetMap administration"
admin.site.site_title = "NetMap"
admin.site.index_title = "Inventory records"

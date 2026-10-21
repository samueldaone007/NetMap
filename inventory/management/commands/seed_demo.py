"""Create a small, fictional network for exploring NetMap."""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventory.models import (
    ChangeLog,
    Connection,
    Device,
    IPAddress,
    ImportBatch,
    Location,
    Outage,
    Port,
    Source,
    Subnet,
)


class Command(BaseCommand):
    help = "Seed a fictional network inventory for local exploration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing inventory records before seeding. Auth users are kept.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write(self.style.WARNING("Clearing existing inventory records..."))
            Outage.objects.all().delete()
            Connection.objects.all().delete()
            Port.objects.all().delete()
            IPAddress.objects.all().delete()
            Device.objects.all().delete()
            Subnet.objects.all().delete()
            Location.objects.all().delete()
            ImportBatch.objects.all().delete()
            ChangeLog.objects.all().delete()

        self.seed()
        self.stdout.write(
            self.style.SUCCESS(
                "Seeded demo inventory: "
                f"{Device.objects.count()} devices, "
                f"{Subnet.objects.count()} subnets, "
                f"{Port.objects.count()} ports, "
                f"{Connection.objects.count()} cables, "
                f"{IPAddress.objects.count()} addresses, "
                f"{Outage.objects.count()} outages."
            )
        )

    def seed(self):
        today = timezone.localdate()
        now = timezone.now()

        locations = {}
        location_data = {
            "r1_fw": (
                "Riverside",
                "Annex",
                "Comms",
                "R1",
                42,
                "Top of cabinet; firewall and edge cabling.",
            ),
            "r1_core": (
                "Riverside",
                "Annex",
                "Comms",
                "R1",
                40,
                "Core switch shelf.",
            ),
            "r1_patch": (
                "Riverside",
                "Annex",
                "Comms",
                "R1",
                10,
                "Structured cabling and floor runs.",
            ),
            "r2_app": (
                "Riverside",
                "Annex",
                "Comms",
                "R2",
                42,
                "Application server shelf.",
            ),
            "r2_db": (
                "Riverside",
                "Annex",
                "Comms",
                "R2",
                41,
                "Database server shelf.",
            ),
            "hilltop": (
                "Hilltop",
                "Cabin",
                "Store",
                "H1",
                10,
                "Small wall cabinet above the store door.",
            ),
        }
        for key, (site, building, room, rack, unit, notes) in location_data.items():
            locations[key], _ = Location.objects.update_or_create(
                site=site,
                building=building,
                room=room,
                rack=rack,
                rack_unit=unit,
                defaults={"notes": notes},
            )

        subnets = {}
        subnet_data = {
            "office": ("10.20.30.0/24", 30, "Office LAN", "10.20.30.1", "Staff and access layer."),
            "server": ("10.20.40.0/24", 40, "Server LAN", "10.20.40.1", "Application and database services."),
            "wireless": ("10.20.50.0/24", 50, "Wireless", "10.20.50.1", "Cabin and yard access points."),
            "management": ("10.20.99.0/24", 99, "Management", "10.20.99.1", "Out-of-band management."),
        }
        for key, (cidr, vlan, name, gateway, purpose) in subnet_data.items():
            subnets[key], _ = Subnet.objects.update_or_create(
                cidr=cidr,
                defaults={
                    "vlan_id": vlan,
                    "name": name,
                    "gateway": gateway,
                    "purpose": purpose,
                },
            )

        device_data = {
            "edge-fw-01": {
                "device_type": Device.Type.FIREWALL,
                "vendor": "Fortinet",
                "model": "FortiGate 60F",
                "serial_number": "NM-FW-001",
                "asset_id": "NM-A-001",
                "hostname": "edge-fw-01.riverside",
                "os_version": "FortiOS 7.4.4",
                "firmware": "7.4.4",
                "management_ip": "10.20.30.10",
                "location": locations["r1_fw"],
                "rack_unit": 42,
                "owner": "Network team",
                "purpose": "Internet edge, site-to-site VPN and firewall policy.",
                "purchase_date": today - timedelta(days=640),
                "warranty_expiry": today + timedelta(days=455),
                "last_verified": today,
                "notes": "Uplink to the provider hand-off is on port 1.",
            },
            "core-sw-01": {
                "device_type": Device.Type.SWITCH,
                "vendor": "Cisco",
                "model": "Catalyst 9200-24P",
                "serial_number": "NM-SW-001",
                "asset_id": "NM-A-002",
                "hostname": "core-sw-01.riverside",
                "os_version": "IOS-XE 17.9.4a",
                "firmware": "17.9.4a",
                "management_ip": "10.20.30.2",
                "location": locations["r1_core"],
                "rack_unit": 40,
                "owner": "Network team",
                "purpose": "Core distribution for Riverside and the cabin link.",
                "purchase_date": today - timedelta(days=720),
                "warranty_expiry": today + timedelta(days=375),
                "last_verified": today,
                "notes": "PoE budget loaded by the cabin access point and office ports.",
            },
            "patch-r1-01": {
                "device_type": Device.Type.PATCH_PANEL,
                "vendor": "Generic",
                "model": "24-port CAT6",
                "serial_number": "NM-PP-001",
                "asset_id": "NM-A-003",
                "hostname": "",
                "management_ip": None,
                "location": locations["r1_patch"],
                "rack_unit": 10,
                "owner": "Facilities",
                "purpose": "Structured cabling for the Riverside rack.",
                "last_verified": today - timedelta(days=2),
                "notes": "PP-01 through PP-12 are labelled at the rail.",
            },
            "srv-app-01": {
                "device_type": Device.Type.SERVER,
                "vendor": "Dell",
                "model": "PowerEdge R650",
                "serial_number": "NM-SRV-001",
                "asset_id": "NM-A-004",
                "hostname": "srv-app-01.riverside",
                "os_version": "Ubuntu 24.04 LTS",
                "firmware": "BIOS 1.9.2",
                "management_ip": "10.20.40.10",
                "location": locations["r2_app"],
                "rack_unit": 42,
                "owner": "Applications",
                "purpose": "Internal application server and job runner.",
                "purchase_date": today - timedelta(days=260),
                "warranty_expiry": today + timedelta(days=835),
                "last_verified": today,
                "notes": "Primary network interface is eth0.",
            },
            "srv-db-01": {
                "device_type": Device.Type.SERVER,
                "vendor": "Dell",
                "model": "PowerEdge R650",
                "serial_number": "NM-SRV-002",
                "asset_id": "NM-A-005",
                "hostname": "srv-db-01.riverside",
                "os_version": "Ubuntu 24.04 LTS",
                "firmware": "BIOS 1.9.2",
                "management_ip": "10.20.40.11",
                "location": locations["r2_db"],
                "rack_unit": 41,
                "owner": "Data",
                "purpose": "PostgreSQL primary for internal services.",
                "purchase_date": today - timedelta(days=260),
                "warranty_expiry": today + timedelta(days=835),
                "last_verified": today,
                "notes": "PSU B failed during the last maintenance window.",
            },
            "ap-hilltop": {
                "device_type": Device.Type.AP,
                "vendor": "Ubiquiti",
                "model": "UniFi U6-Pro",
                "serial_number": "NM-AP-001",
                "asset_id": "NM-A-006",
                "hostname": "ap-hilltop.riverside",
                "os_version": "UniFi 6.6.65",
                "firmware": "6.6.65",
                "management_ip": "10.20.50.50",
                "location": locations["hilltop"],
                "rack_unit": 10,
                "owner": "Network team",
                "purpose": "Wireless coverage for the cabin and yard.",
                "purchase_date": today - timedelta(days=410),
                "warranty_expiry": today + timedelta(days=320),
                "last_verified": today - timedelta(days=5),
                "notes": "Fed from PP-02 in the Riverside rack.",
            },
            "UNNAMED-001": {
                "device_type": Device.Type.OTHER,
                "vendor": "",
                "model": "",
                "serial_number": None,
                "asset_id": None,
                "hostname": "",
                "management_ip": None,
                "location": None,
                "rack_unit": None,
                "owner": "",
                "purpose": "",
                "last_verified": None,
                "needs_identifying": True,
                "source": Source.IMPORT,
                "notes": "Free-text reference from the last import; identify on the next walk.",
            },
        }
        devices = {}
        for name, defaults in device_data.items():
            devices[name], _ = Device.objects.update_or_create(
                name=name, defaults=defaults
            )

        for number in range(1, 25):
            Port.objects.update_or_create(
                device=devices["core-sw-01"],
                label=f"Gi1/0/{number}",
                defaults={
                    "port_type": Port.Type.ETHERNET,
                    "speed": "1G",
                    "poe": number <= 12,
                    "access_vlan": 30,
                    "status": Port.Status.UP if number <= 5 else Port.Status.FREE,
                },
            )
        for number in range(1, 9):
            Port.objects.update_or_create(
                device=devices["edge-fw-01"],
                label=f"port{number}",
                defaults={
                    "port_type": Port.Type.ETHERNET if number > 1 else Port.Type.WAN,
                    "speed": "1G",
                    "status": Port.Status.UP if number == 1 else Port.Status.FREE,
                },
            )
        for label, speed, status in (
            ("eth0", "10G", Port.Status.UP),
            ("eth1", "10G", Port.Status.FREE),
            ("eth2", "1G", Port.Status.FREE),
            ("eth3", "1G", Port.Status.FREE),
        ):
            Port.objects.update_or_create(
                device=devices["srv-app-01"],
                label=label,
                defaults={
                    "port_type": Port.Type.ETHERNET,
                    "speed": speed,
                    "status": status,
                },
            )
            Port.objects.update_or_create(
                device=devices["srv-db-01"],
                label=label,
                defaults={
                    "port_type": Port.Type.ETHERNET,
                    "speed": speed,
                    "status": status if label == "eth0" else Port.Status.FREE,
                },
            )
        Port.objects.update_or_create(
            device=devices["ap-hilltop"],
            label="eth0",
            defaults={
                "port_type": Port.Type.ETHERNET,
                "speed": "1G",
                "poe": True,
                "access_vlan": 50,
                "status": Port.Status.UP,
            },
        )
        for number in range(1, 13):
            Port.objects.update_or_create(
                device=devices["patch-r1-01"],
                label=f"PP-{number:02d}",
                defaults={
                    "port_type": Port.Type.PATCH,
                    "status": (
                        Port.Status.UP if number <= 2 else Port.Status.FREE
                    ),
                },
            )

        def port(device_name, label):
            return Port.objects.get(device=devices[device_name], label=label)

        cable_data = [
            (
                port("edge-fw-01", "port1"),
                port("core-sw-01", "Gi1/0/1"),
                "C-001",
                "Firewall uplink.",
            ),
            (
                port("core-sw-01", "Gi1/0/2"),
                port("srv-app-01", "eth0"),
                "C-002",
                "Application server access.",
            ),
            (
                port("core-sw-01", "Gi1/0/3"),
                port("srv-db-01", "eth0"),
                "C-003",
                "Database server access.",
            ),
            (
                port("core-sw-01", "Gi1/0/4"),
                port("patch-r1-01", "PP-01"),
                "C-004",
                "Rack patching to the cabin run.",
            ),
            (
                port("patch-r1-01", "PP-02"),
                port("ap-hilltop", "eth0"),
                "C-005",
                "Cabin access point run.",
            ),
            (
                port("core-sw-01", "Gi1/0/5"),
                None,
                "C-006",
                "Untraced run; far end still unknown.",
            ),
        ]
        for port_a, port_b, cable_label, notes in cable_data:
            Connection.objects.update_or_create(
                port_a=port_a,
                defaults={
                    "port_b": port_b,
                    "cable_label": cable_label,
                    "notes": notes,
                    "source": Source.MANUAL,
                },
            )

        ip_data = [
            ("10.20.30.1", "office", None, "Gateway", IPAddress.Status.RESERVED),
            ("10.20.30.2", "office", "core-sw-01", "core-sw-01.riverside", IPAddress.Status.USED),
            ("10.20.30.10", "office", "edge-fw-01", "edge-fw-01.riverside", IPAddress.Status.USED),
            ("10.20.30.100", "office", None, "", IPAddress.Status.FREE),
            ("10.20.40.1", "server", None, "Gateway", IPAddress.Status.RESERVED),
            ("10.20.40.10", "server", "srv-app-01", "srv-app-01.riverside", IPAddress.Status.USED),
            ("10.20.40.11", "server", "srv-db-01", "srv-db-01.riverside", IPAddress.Status.USED),
            ("10.20.40.12", "server", None, "", IPAddress.Status.RESERVED),
            ("10.20.50.1", "wireless", None, "Gateway", IPAddress.Status.RESERVED),
            ("10.20.50.50", "wireless", "ap-hilltop", "ap-hilltop.riverside", IPAddress.Status.USED),
            ("10.20.99.1", "management", None, "Gateway", IPAddress.Status.RESERVED),
        ]
        for address, subnet_key, device_name, hostname, status in ip_data:
            IPAddress.objects.update_or_create(
                address=address,
                defaults={
                    "subnet": subnets[subnet_key],
                    "device": devices[device_name] if device_name else None,
                    "hostname": hostname,
                    "status": status,
                    "source": Source.MANUAL,
                    "last_verified": today,
                },
            )

        Outage.objects.get_or_create(
            device=devices["srv-db-01"],
            cause="PSU failure",
            defaults={
                "started": now - timedelta(hours=3, minutes=20),
                "ended": None,
                "notes": "PSU B failed. Replacement is on order; the server is still running on PSU A.",
            },
        )
        Outage.objects.get_or_create(
            device=devices["ap-hilltop"],
            cause="Cable damaged at cabinet",
            defaults={
                "started": now - timedelta(days=10),
                "ended": now - timedelta(days=9, hours=21),
                "notes": "PP-02 patched to a spare run and the access point came back.",
            },
        )

        positions = {
            "edge-fw-01": (180, 160),
            "core-sw-01": (380, 180),
            "patch-r1-01": (180, 380),
            "srv-app-01": (620, 100),
            "srv-db-01": (620, 280),
            "ap-hilltop": (860, 200),
            "UNNAMED-001": (860, 360),
        }
        for name, (x, y) in positions.items():
            Device.objects.filter(name=name).update(graph_x=x, graph_y=y)

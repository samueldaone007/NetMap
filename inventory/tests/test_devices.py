from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Connection, Device, IPAddress, Location, Outage, Port, Subnet


class DeviceDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.client.force_login(self.user)
        self.location = Location.objects.create(
            site="Riverside", building="Annex", room="Comms", rack="R1", rack_unit=10
        )
        self.other_location = Location.objects.create(
            site="Riverside", building="Annex", room="Comms", rack="R1", rack_unit=20
        )
        self.device = Device.objects.create(
            name="core-sw-01",
            device_type=Device.Type.SWITCH,
            vendor="Cisco",
            model="C9200",
            serial_number="SN-01",
            management_ip="10.20.30.2",
            location=self.location,
            rack_unit=10,
            purpose="Core distribution",
        )
        self.other = Device.objects.create(
            name="srv-01",
            device_type=Device.Type.SERVER,
            location=self.other_location,
            rack_unit=20,
        )
        self.port = Port.objects.create(device=self.device, label="Gi0/1", status=Port.Status.UP)
        self.other_port = Port.objects.create(device=self.other, label="eth0")
        self.connection = Connection.objects.create(
            port_a=self.port, port_b=self.other_port, cable_label="C-001"
        )
        self.subnet = Subnet.objects.create(cidr="10.20.30.0/24", name="Office", vlan_id=30)
        self.ip = IPAddress.objects.create(
            address="10.20.30.20",
            subnet=self.subnet,
            device=self.device,
            hostname="core-sw-01.office",
            status=IPAddress.Status.USED,
        )
        Outage.objects.create(device=self.device, started=timezone.now(), cause="Fan failure")

    def test_device_detail_shows_ports_addresses_cables_and_timeline(self):
        response = self.client.get(reverse("device_detail", args=[self.device.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "core-sw-01")
        self.assertContains(response, "Gi0/1")
        self.assertContains(response, "10.20.30.20")
        self.assertContains(response, "C-001")
        self.assertContains(response, "Fan failure")
        self.assertContains(response, "Change trail")
        self.assertContains(response, "Open outage")

    def test_device_edit_updates_and_logs_change(self):
        response = self.client.post(
            reverse("device_edit", args=[self.device.pk]),
            {
                "name": "core-sw-01",
                "device_type": "switch",
                "vendor": "Juniper",
                "model": "EX4300",
                "serial_number": "SN-01",
                "asset_id": "",
                "hostname": "",
                "os_version": "",
                "firmware": "",
                "management_ip": "10.20.30.2",
                "location": self.location.pk,
                "owner": "",
                "purpose": "Core distribution",
                "purchase_date": "",
                "warranty_expiry": "",
                "status": "active",
                "notes": "",
                "needs_identifying": "",
                "last_verified": "",
            },
        )
        self.assertRedirects(response, reverse("device_detail", args=[self.device.pk]))
        self.device.refresh_from_db()
        self.assertEqual(self.device.vendor, "Juniper")
        self.assertTrue(
            self.device.notes == ""
        )
        from inventory.models import ChangeLog

        self.assertTrue(
            ChangeLog.objects.filter(
                object_type="Device", object_id=str(self.device.pk), field="vendor"
            ).exists()
        )

    def test_verify_marks_the_device_today(self):
        response = self.client.post(reverse("device_verify", args=[self.device.pk]))
        self.assertRedirects(response, reverse("device_detail", args=[self.device.pk]))
        self.device.refresh_from_db()
        self.assertEqual(self.device.last_verified, timezone.localdate())

    def test_rack_view_groups_locations_into_one_elevation(self):
        unpositioned_location = Location.objects.create(
            site="Riverside", building="Annex", room="Comms", rack="R1"
        )
        Device.objects.create(
            name="patch-01",
            device_type=Device.Type.PATCH_PANEL,
            location=unpositioned_location,
        )
        Device.objects.create(name="loose-01", device_type=Device.Type.OTHER)
        response = self.client.get(reverse("rack_view"))
        self.assertEqual(response.status_code, 200)
        racks = response.context["racks"]
        self.assertEqual(len(racks), 1)
        rack = racks[0]
        self.assertEqual(rack.height, 42)
        self.assertEqual(rack.device_count, 3)
        self.assertEqual(rack.used_units, 2)
        self.assertEqual(len(rack.unpositioned), 1)
        self.assertEqual(len(response.context["unplaced"]), 1)
        self.assertContains(response, "core-sw-01")
        self.assertContains(response, "srv-01")
        self.assertContains(response, "U10")

    def test_rack_view_flags_two_devices_at_one_unit(self):
        duplicate_location = Location.objects.create(
            site="Riverside", building="Annex", room="Comms", rack="R1", rack_unit=10
        )
        Device.objects.create(
            name="duplicate-01",
            device_type=Device.Type.SERVER,
            location=duplicate_location,
            rack_unit=10,
        )
        response = self.client.get(reverse("rack_view"))
        rack = response.context["racks"][0]
        self.assertEqual(len(rack.conflicts), 1)
        self.assertContains(response, "more than one device")

    def test_rack_view_site_filter(self):
        hilltop = Location.objects.create(site="Hilltop", room="Store", rack="H1", rack_unit=1)
        Device.objects.create(
            name="hilltop-ap", device_type=Device.Type.AP, location=hilltop, rack_unit=1
        )
        response = self.client.get(reverse("rack_view"), {"site": "Hilltop"})
        self.assertEqual([rack.location.site for rack in response.context["racks"]], ["Hilltop"])
        self.assertContains(response, "hilltop-ap")
        self.assertNotContains(response, "core-sw-01")

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import Device, IPAddress, Location, Port, Subnet


class TableTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.client.force_login(self.user)
        self.location = Location.objects.create(site="Lagos", building="DC1", rack="A", rack_unit=12)
        self.device = Device.objects.create(
            name="core-sw-01", device_type=Device.Type.SWITCH, location=self.location
        )

    def test_device_table_renders_inline_cells(self):
        response = self.client.get(reverse("device_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "core-sw-01")
        self.assertContains(response, f"/tables/devices/{self.device.pk}/cell/name/")
        self.assertContains(response, "Paste rows")

    def test_search_filters_devices(self):
        Device.objects.create(name="edge-rtr-01", device_type=Device.Type.ROUTER)
        response = self.client.get(reverse("device_list"), {"q": "edge"})
        self.assertContains(response, "edge-rtr-01")
        self.assertNotContains(response, "core-sw-01")

    def test_inline_edit_updates_a_field(self):
        url = reverse("table_cell", args=["devices", self.device.pk, "name"])
        response = self.client.post(url, {"name": "core-sw-renamed"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.device.refresh_from_db()
        self.assertEqual(self.device.name, "core-sw-renamed")
        self.assertContains(response, "core-sw-renamed")

    def test_inline_edit_can_be_cancelled(self):
        url = reverse("table_cell", args=["devices", self.device.pk, "vendor"])
        response = self.client.get(url, {"display": "1"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "cell-edit-trigger")

    def test_inline_edit_rejects_invalid_ip(self):
        url = reverse("table_cell", args=["devices", self.device.pk, "management_ip"])
        response = self.client.post(url, {"management_ip": "not-an-ip"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Enter a valid IP")
        self.device.refresh_from_db()
        self.assertIsNone(self.device.management_ip)

    def test_connection_table_is_available(self):
        response = self.client.get(reverse("connection_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No lines on this map yet")


class PasteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.client.force_login(self.user)
        self.device = Device.objects.create(name="core-sw-01", device_type=Device.Type.SWITCH)
        self.subnet = Subnet.objects.create(cidr="192.168.20.0/24", name="Office", vlan_id=20)

    def test_paste_devices_with_header(self):
        text = "name\tdevice_type\tvendor\tlocation\nsrv-01\tserver\tDell\t"
        response = self.client.post(reverse("table_paste", args=["devices"]), {"paste_text": text})
        self.assertRedirects(response, reverse("device_list"))
        self.assertTrue(Device.objects.filter(name="srv-01", device_type="server").exists())

    def test_paste_ips_links_device(self):
        text = f"192.168.20.10\t192.168.20.0/24\t{self.device.name}\tcore.local\tused"
        response = self.client.post(reverse("table_paste", args=["ips"]), {"paste_text": text})
        self.assertEqual(response.status_code, 302)
        ip = IPAddress.objects.get(address="192.168.20.10")
        self.assertEqual(ip.device, self.device)

    def test_paste_ports_expands_ranges(self):
        text = "core-sw-01\tLAN2-5\tethernet\t1G\tno\t20\t\tfree"
        response = self.client.post(reverse("table_paste", args=["ports"]), {"paste_text": text})
        self.assertEqual(response.status_code, 302)
        labels = list(Port.objects.filter(device=self.device).values_list("label", flat=True))
        self.assertEqual(labels, ["LAN2", "LAN3", "LAN4", "LAN5"])

    def test_paste_errors_leave_nothing_behind(self):
        text = "core-sw-01\tLAN1\tethernet\t1G\tno\t9999\t\tfree"
        response = self.client.post(reverse("table_paste", args=["ports"]), {"paste_text": text})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing was saved")
        self.assertEqual(Port.objects.count(), 0)

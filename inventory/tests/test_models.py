from django.core.exceptions import ValidationError
from django.test import TestCase

from inventory.models import Connection, Device, IPAddress, Location, Port, Subnet


class ModelValidationTests(TestCase):
    def setUp(self):
        self.subnet = Subnet.objects.create(
            cidr="192.168.10.0/24", vlan_id=20, name="Office", gateway="192.168.10.1"
        )
        self.device = Device.objects.create(name="core-sw-01", device_type=Device.Type.SWITCH)

    def test_subnet_cidr_is_normalised(self):
        subnet = Subnet(cidr="10.20.30.99/24", name="Normalised")
        subnet.full_clean()
        self.assertEqual(subnet.cidr, "10.20.30.0/24")

    def test_subnet_rejects_invalid_cidr(self):
        with self.assertRaises(ValidationError):
            Subnet(cidr="not-a-subnet", name="Broken").full_clean()

    def test_gateway_must_be_inside_subnet(self):
        with self.assertRaises(ValidationError):
            Subnet(cidr="10.0.0.0/24", name="Bad gateway", gateway="10.0.1.1").full_clean()

    def test_ip_must_fall_inside_subnet(self):
        with self.assertRaises(ValidationError):
            IPAddress(address="10.9.9.9", subnet=self.subnet).full_clean()

    def test_network_and_broadcast_are_not_assignable(self):
        for address in ("192.168.10.0", "192.168.10.255"):
            with self.assertRaises(ValidationError):
                IPAddress(address=address, subnet=self.subnet).full_clean()

    def test_ip_is_canonicalised_and_can_be_assigned(self):
        ip = IPAddress(address="192.168.10.20", subnet=self.subnet, device=self.device)
        ip.full_clean()
        ip.save()
        self.assertEqual(str(ip), "192.168.10.20")
        self.assertTrue(ip.is_usable)

    def test_connection_cannot_join_a_port_to_itself(self):
        port = Port.objects.create(device=self.device, label="Gi0/1")
        with self.assertRaises(ValidationError):
            Connection(port_a=port, port_b=port).full_clean()

    def test_port_usage_counts_connections_and_statuses(self):
        free = Port.objects.create(device=self.device, label="Gi0/1", status=Port.Status.FREE)
        used = Port.objects.create(device=self.device, label="Gi0/2", status=Port.Status.UP)
        other = Device.objects.create(name="srv-01")
        far = Port.objects.create(device=other, label="eth0")
        Connection.objects.create(port_a=free, port_b=far)
        self.assertEqual(self.device.port_usage(), (2, 2))
        self.assertTrue(free.is_used)
        self.assertEqual(other.port_usage(), (1, 1))
        self.assertEqual(Port.objects.get(pk=used.pk).label, "Gi0/2")

    def test_location_label_and_rack_path(self):
        location = Location(site="Lagos", building="DC1", room="Hall", rack="A", rack_unit=12)
        self.assertIn("U12", str(location))
        self.assertEqual(location.rack_path, "Lagos · DC1 · Hall · A")

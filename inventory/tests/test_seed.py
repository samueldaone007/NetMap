from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from inventory.models import Connection, Device, IPAddress, Outage, Port, Subnet


class SeedDemoTests(TestCase):
    def run_seed(self, *args):
        output = StringIO()
        call_command("seed_demo", *args, stdout=output, verbosity=0)
        return output.getvalue()

    def test_seed_creates_a_rich_but_small_demo(self):
        self.run_seed()
        self.assertEqual(Device.objects.count(), 7)
        self.assertEqual(Subnet.objects.count(), 4)
        self.assertEqual(Port.objects.count(), 53)
        self.assertEqual(Connection.objects.count(), 6)
        self.assertEqual(IPAddress.objects.count(), 11)
        self.assertEqual(Outage.objects.filter(ended__isnull=True).count(), 1)
        self.assertTrue(Device.objects.get(name="UNNAMED-001").needs_identifying)
        self.assertTrue(
            Device.objects.filter(graph_x__isnull=False, graph_y__isnull=False).exists()
        )

    def test_seed_is_idempotent(self):
        self.run_seed()
        counts = (
            Device.objects.count(),
            Subnet.objects.count(),
            Port.objects.count(),
            Connection.objects.count(),
            IPAddress.objects.count(),
            Outage.objects.count(),
        )
        self.run_seed()
        self.assertEqual(
            counts,
            (
                Device.objects.count(),
                Subnet.objects.count(),
                Port.objects.count(),
                Connection.objects.count(),
                IPAddress.objects.count(),
                Outage.objects.count(),
            ),
        )

    def test_reset_clears_inventory_but_keeps_the_seed(self):
        Device.objects.create(name="scratch-device")
        self.run_seed("--reset")
        self.assertFalse(Device.objects.filter(name="scratch-device").exists())
        self.assertTrue(Device.objects.filter(name="core-sw-01").exists())

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import IPAddress, Subnet
from inventory.services.subnets import find_next_free


class SubnetPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.client.force_login(self.user)
        self.subnet = Subnet.objects.create(
            cidr="192.168.50.0/29", name="Lab", vlan_id=50, gateway="192.168.50.1"
        )

    def test_subnet_list_lists_district(self):
        response = self.client.get(reverse("subnet_list"))
        self.assertContains(response, "Lab")
        self.assertContains(response, "192.168.50.0/29")

    def test_subnet_detail_renders_usable_grid(self):
        response = self.client.get(reverse("subnet_detail", args=[self.subnet.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ip-unrecorded", count=6)
        self.assertContains(response, "192.168.50.6")

    def test_next_free_returns_first_unrecorded_host(self):
        self.assertEqual(find_next_free(self.subnet), "192.168.50.1")
        IPAddress.objects.create(address="192.168.50.1", subnet=self.subnet)
        self.assertEqual(find_next_free(self.subnet), "192.168.50.2")

    def test_next_free_button_logs_free_address(self):
        response = self.client.post(reverse("subnet_next_free", args=[self.subnet.pk]))
        self.assertRedirects(response, reverse("subnet_detail", args=[self.subnet.pk]))
        ip = IPAddress.objects.get(subnet=self.subnet)
        self.assertEqual(ip.address, "192.168.50.1")
        self.assertEqual(ip.status, IPAddress.Status.FREE)

    def test_next_free_when_full(self):
        for last in range(1, 7):
            IPAddress.objects.create(address=f"192.168.50.{last}", subnet=self.subnet)
        response = self.client.post(reverse("subnet_next_free", args=[self.subnet.pk]))
        self.assertRedirects(response, reverse("subnet_detail", args=[self.subnet.pk]))
        self.assertEqual(self.subnet.ips.count(), 6)

    def test_large_subnet_is_chunked(self):
        subnet = Subnet.objects.create(cidr="10.10.0.0/16", name="Big")
        response = self.client.get(reverse("subnet_detail", args=[subnet.pk]))
        self.assertContains(response, "Showing 1–256 of 65534")
        self.assertContains(response, "Next block")

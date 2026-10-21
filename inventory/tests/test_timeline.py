from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import ChangeLog, Connection, Device, Outage, Port


class TimelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "keeper", password="test-password-123"
        )
        self.client.force_login(self.user)
        self.device = Device.objects.create(
            name="core-sw-01", device_type=Device.Type.SWITCH
        )
        self.other = Device.objects.create(
            name="srv-app-01", device_type=Device.Type.SERVER
        )
        self.port_a = Port.objects.create(device=self.device, label="Gi0/1")
        self.port_b = Port.objects.create(device=self.other, label="eth0")
        self.connection = Connection.objects.create(
            port_a=self.port_a, port_b=self.port_b, cable_label="C-001"
        )
        self.outage = Outage.objects.create(
            device=self.device,
            started=timezone.now() - timedelta(hours=2),
            cause="Power supply failure",
            notes="Replacement PSU ordered.",
        )

    def test_timeline_shows_changes_and_open_outages(self):
        response = self.client.get(reverse("timeline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Power supply failure")
        self.assertContains(response, "core-sw-01")
        self.assertContains(response, "Open right now")
        self.assertEqual(response.context["stats"]["open"], 1)
        kinds = {
            event["kind"]
            for group in response.context["groups"]
            for event in group["events"]
        }
        self.assertEqual(kinds, {"change", "outage"})

    def test_record_filter_shows_only_outages(self):
        response = self.client.get(reverse("timeline"), {"record": "Outage"})
        events = [
            event for group in response.context["groups"] for event in group["events"]
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "outage")
        self.assertNotContains(response, "Record created in the inventory.")

    def test_search_matches_outage_cause(self):
        response = self.client.get(
            reverse("timeline"), {"q": "power supply", "record": "Outage"}
        )
        self.assertEqual(response.context["event_total"], 1)
        self.assertContains(response, "Power supply failure")

    def test_create_outage_from_device_redirects_to_device(self):
        response = self.client.post(
            reverse("outage_create"),
            {
                "device": self.device.pk,
                "connection": "",
                "started": "2026-10-20T09:30",
                "ended": "",
                "cause": "Firmware crash",
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("device_detail", args=[self.device.pk]))
        outage = Outage.objects.get(cause="Firmware crash")
        self.assertEqual(outage.device, self.device)
        self.assertTrue(outage.is_open)

    def test_create_outage_requires_exactly_one_subject(self):
        response = self.client.post(
            reverse("outage_create"),
            {
                "device": self.device.pk,
                "connection": self.connection.pk,
                "started": "2026-10-20T09:30",
                "ended": "",
                "cause": "Ambiguous failure",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose either a device or a connection")
        self.assertFalse(Outage.objects.filter(cause="Ambiguous failure").exists())

    def test_edit_outage_keeps_the_change_record(self):
        response = self.client.post(
            reverse("outage_edit", args=[self.outage.pk]),
            {
                "device": self.device.pk,
                "connection": "",
                "started": self.outage.started.strftime("%Y-%m-%dT%H:%M"),
                "ended": "",
                "cause": "Power supply failure (confirmed)",
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("device_detail", args=[self.device.pk]))
        self.outage.refresh_from_db()
        self.assertEqual(self.outage.cause, "Power supply failure (confirmed)")
        self.assertTrue(
            ChangeLog.objects.filter(
                object_type="Outage",
                object_id=str(self.outage.pk),
                field="cause",
            ).exists()
        )

    def test_close_outage_stamps_time_and_returns_to_next_page(self):
        next_url = f"{reverse('timeline')}?record=Outage"
        response = self.client.post(
            reverse("outage_close", args=[self.outage.pk]),
            {"next": next_url},
        )
        self.assertRedirects(response, next_url)
        self.outage.refresh_from_db()
        self.assertIsNotNone(self.outage.ended)
        self.assertFalse(self.outage.is_open)
        self.assertTrue(
            ChangeLog.objects.filter(
                object_type="Outage",
                object_id=str(self.outage.pk),
                field="ended",
            ).exists()
        )

    def test_timeline_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("timeline"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('timeline')}")

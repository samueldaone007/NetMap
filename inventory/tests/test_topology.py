import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Connection, Device, Location, Outage, Port


class TopologyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.client.force_login(self.user)
        self.site_a = Location.objects.create(site="Riverside", building="Annex", rack="R1")
        self.site_b = Location.objects.create(site="Hilltop", building="Cabin", rack="R2")
        self.switch = Device.objects.create(
            name="core-sw-01",
            device_type=Device.Type.SWITCH,
            location=self.site_a,
        )
        self.server = Device.objects.create(
            name="srv-01",
            device_type=Device.Type.SERVER,
            location=self.site_a,
        )
        self.remote = Device.objects.create(
            name="remote-01",
            device_type=Device.Type.ROUTER,
            location=self.site_b,
        )
        self.switch_port = Port.objects.create(device=self.switch, label="Gi0/1")
        self.server_port = Port.objects.create(device=self.server, label="eth0")
        self.remote_port = Port.objects.create(device=self.remote, label="wan0")
        Connection.objects.create(
            port_a=self.switch_port,
            port_b=self.server_port,
            cable_label="C-100",
        )
        self.unknown = Connection.objects.create(port_a=self.remote_port)
        Outage.objects.create(device=self.server, started=timezone.now(), cause="PSU failure")

    def test_map_renders_graph_nodes_edges_unknowns_and_outages(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        graph = response.context["graph"]
        self.assertEqual(len([node for node in graph["nodes"] if node["kind"] == "device"]), 3)
        self.assertEqual(len(graph["edges"]), 2)
        self.assertEqual(len([node for node in graph["nodes"] if node["kind"] == "unknown"]), 1)
        self.assertEqual(graph["stats"]["outages"], 1)
        unknown = next(node for node in graph["nodes"] if node["kind"] == "unknown")
        self.assertEqual(unknown["label"], "Unknown far end")
        edge = next(edge for edge in graph["edges"] if edge["unknown"])
        self.assertEqual(edge["target"], unknown["id"])
        self.assertContains(response, "topology-data")

    def test_filters_narrow_the_graph(self):
        response = self.client.get(reverse("dashboard"), {"site": "Hilltop"})
        graph = response.context["graph"]
        self.assertEqual(
            [node["id"] for node in graph["nodes"] if node["kind"] == "device"],
            [str(self.remote.pk)],
        )
        self.assertEqual(len(graph["edges"]), 1)
        self.assertTrue(graph["edges"][0]["unknown"])

        response = self.client.get(reverse("dashboard"), {"type": "server"})
        graph = response.context["graph"]
        self.assertEqual(
            [node["label"] for node in graph["nodes"] if node["kind"] == "device"],
            ["srv-01"],
        )
        self.assertEqual(graph["edges"], [])

    def test_isolated_filter_and_unknown_toggle(self):
        isolated = Device.objects.create(name="loose-ap", device_type=Device.Type.AP)
        response = self.client.get(reverse("dashboard"), {"isolated": "1"})
        self.assertIn(str(isolated.pk), [node["id"] for node in response.context["graph"]["nodes"]])
        response = self.client.get(reverse("dashboard"), {"isolated": "0"})
        ids = [node["id"] for node in response.context["graph"]["nodes"] if node["kind"] == "device"]
        self.assertNotIn(str(isolated.pk), ids)
        response = self.client.get(reverse("dashboard"), {"unknown": "0"})
        self.assertFalse(
            [node for node in response.context["graph"]["nodes"] if node["kind"] == "unknown"]
        )

    def test_empty_map_keeps_import_and_add_actions(self):
        Connection.objects.all().delete()
        Device.objects.all().delete()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "No lines on this map yet.")
        self.assertContains(response, reverse("import_index"))
        self.assertEqual(response.context["graph"]["nodes"], [])

    def test_saved_positions_are_persisted(self):
        positions = {
            str(self.switch.pk): {"x": 10, "y": 20},
            str(self.server.pk): {"x": 130, "y": 40},
            str(self.remote.pk): {"x": 230, "y": 90},
        }
        response = self.client.post(
            reverse("topology_layout"),
            data=json.dumps({"positions": positions}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.switch.refresh_from_db()
        self.assertEqual((self.switch.graph_x, self.switch.graph_y), (10.0, 20.0))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["graph"]["layout"], "saved")

    def test_saved_layout_can_be_requested_even_when_partly_blank(self):
        self.switch.graph_x, self.switch.graph_y = 30, 40
        self.switch.save(update_fields=["graph_x", "graph_y"])
        response = self.client.get(reverse("dashboard"), {"layout": "saved"})
        self.assertEqual(response.context["graph"]["layout"], "saved")
        self.assertEqual(response.context["graph"]["savedCount"], 1)

    def test_layout_endpoint_rejects_bad_values(self):
        response = self.client.post(
            reverse("topology_layout"),
            data=json.dumps({"positions": {str(self.switch.pk): {"x": "nope", "y": 2}}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            reverse("topology_layout"),
            data=json.dumps({"positions": {"999999": {"x": 1, "y": 2}}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_layout_endpoint_requires_post_and_login(self):
        response = self.client.get(reverse("topology_layout"))
        self.assertEqual(response.status_code, 405)
        self.client.logout()
        response = self.client.post(
            reverse("topology_layout"),
            data=json.dumps({"positions": {str(self.switch.pk): {"x": 1, "y": 2}}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

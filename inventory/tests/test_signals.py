from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import ChangeLog, Device, Port


class ChangeLogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.device = Device.objects.create(name="sw-01", vendor="Cisco", device_type="switch")

    def test_create_is_logged(self):
        entry = ChangeLog.objects.filter(object_type="Device", object_id=str(self.device.pk)).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, ChangeLog.Action.CREATE)

    def test_field_changes_are_logged_with_old_and_new(self):
        ChangeLog.objects.all().delete()
        self.device.vendor = "Aruba"
        self.device.status = "spare"
        self.device.save()
        entries = ChangeLog.objects.filter(
            object_type="Device", object_id=str(self.device.pk), action=ChangeLog.Action.UPDATE
        )
        by_field = {entry.field: entry for entry in entries}
        self.assertEqual(by_field["vendor"].old_value, "Cisco")
        self.assertEqual(by_field["vendor"].new_value, "Aruba")
        self.assertEqual(by_field["status"].new_value, "Spare")

    def test_no_change_writes_nothing(self):
        ChangeLog.objects.all().delete()
        self.device.save()
        self.assertEqual(ChangeLog.objects.count(), 0)

    def test_inline_edit_records_request_user(self):
        self.client.force_login(self.user)
        url = reverse("table_cell", args=["devices", self.device.pk, "vendor"])
        response = self.client.post(url, {"vendor": "Juniper"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        entry = ChangeLog.objects.get(
            object_type="Device", field="vendor", action=ChangeLog.Action.UPDATE
        )
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.new_value, "Juniper")

    def test_delete_is_logged(self):
        port = Port.objects.create(device=self.device, label="Gi0/1")
        port_id = port.pk
        ChangeLog.objects.all().delete()
        port.delete()
        entry = ChangeLog.objects.get(object_type="Port", object_id=str(port_id))
        self.assertEqual(entry.action, ChangeLog.Action.DELETE)

    def test_changed_foreign_key_is_readable(self):
        other = Device.objects.create(name="sw-02")
        ChangeLog.objects.all().delete()
        port = Port.objects.create(device=self.device, label="Gi0/2")
        port.device = other
        port.save()
        entry = ChangeLog.objects.get(object_type="Port", field="device")
        self.assertEqual(entry.old_value, str(self.device.pk))
        self.assertEqual(entry.new_value, str(other.pk))

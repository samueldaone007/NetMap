import tempfile
from datetime import date, datetime
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from inventory.imports import (
    ImportEngine,
    ImportUndoError,
    undo_import,
)
from inventory.models import ChangeLog, Connection, Device, ImportBatch, Port


def workbook_bytes(rows, sheet="Servers"):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    for row in rows:
        worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ImportEngineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.device = Device.objects.create(name="core-sw-01", device_type=Device.Type.SWITCH)

    def make_batch(self, target, mapping, rows, sheet="Sheet1", has_header=False):
        batch = ImportBatch(
            uploaded_file=ContentFile(workbook_bytes(rows, sheet), name="book.xlsx"),
            original_name="book.xlsx",
            sheet_name=sheet,
            target_type=target,
            has_header=has_header,
            mapping={str(key): value for key, value in mapping.items()},
            uploaded_by=self.user,
        )
        batch.save()
        return batch

    def test_nil_and_na_become_empty(self):
        batch = self.make_batch(
            "devices",
            {0: "name", 1: "serial_number", 2: "vendor"},
            [["srv-01", "SN-1", "NIL"], ["srv-02", "SN-2", "n/a"]],
        )
        result, _ = ImportEngine(batch).commit()
        self.assertFalse(result.has_errors)
        self.assertEqual(Device.objects.get(name="srv-01").vendor, "")
        self.assertEqual(Device.objects.get(name="srv-02").vendor, "")

    def test_csv_uses_the_same_cleanup_and_mapping(self):
        batch = ImportBatch(
            uploaded_file=ContentFile(
                b'name,serial,vendor\n" csv-server ","SN-CSV"," NIL "\n',
                name="book.csv",
            ),
            original_name="book.csv",
            sheet_name="CSV",
            target_type="devices",
            has_header=True,
            mapping={"0": "name", "1": "serial_number", "2": "vendor"},
            uploaded_by=self.user,
        )
        batch.save()
        result, _ = ImportEngine(batch).commit()
        self.assertFalse(result.has_errors)
        device = Device.objects.get(serial_number="SN-CSV")
        self.assertEqual(device.name, "csv-server")
        self.assertEqual(device.vendor, "")

    def test_date_damaged_port_label_is_flagged_not_imported(self):
        batch = self.make_batch(
            "ports",
            {0: "device", 1: "label"},
            [["core-sw-01", datetime(2024, 2, 24)]],
        )
        result = ImportEngine(batch).run()
        self.assertTrue(result.has_errors)
        self.assertIn("looks like a date", " ".join(result.rows[0].errors))
        self.assertEqual(Port.objects.count(), 0)

    def test_excel_serial_number_in_text_column_is_flagged(self):
        batch = self.make_batch(
            "ports",
            {0: "device", 1: "label"},
            [["core-sw-01", 45346]],
        )
        result = ImportEngine(batch).run()
        self.assertTrue(result.has_errors)
        self.assertIn("number/serial", result.rows[0].errors[0])

    def test_port_ranges_expand_in_preview_and_on_save(self):
        batch = self.make_batch(
            "ports",
            {0: "device", 1: "label", 2: "status"},
            [["core-sw-01", "LAN2-4", "free"]],
        )
        preview = ImportEngine(batch).run()
        self.assertFalse(preview.has_errors)
        self.assertEqual(preview.rows[0].expanded, "LAN2, LAN3, LAN4")
        result, _ = ImportEngine(batch).commit()
        self.assertEqual(result.created_count, 3)
        self.assertEqual(
            sorted(Port.objects.filter(device=self.device).values_list("label", flat=True)),
            ["LAN2", "LAN3", "LAN4"],
        )

    def test_matching_uses_serial_before_name(self):
        Device.objects.create(name="original", serial_number="SER-9", vendor="Old")
        batch = self.make_batch(
            "devices",
            {0: "name", 1: "serial_number", 2: "vendor"},
            [["renamed", "SER-9", "New"]],
        )
        result, _ = ImportEngine(batch).commit()
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(Device.objects.filter(serial_number="SER-9").count(), 1)
        device = Device.objects.get(serial_number="SER-9")
        self.assertEqual(device.name, "renamed")
        self.assertEqual(device.vendor, "New")

    def test_placeholder_rows_are_not_duplicated_on_reimport(self):
        rows = [["", "", "Some notes"]]
        mapping = {0: "name", 1: "serial_number", 2: "notes"}
        first = self.make_batch("devices", mapping, rows)
        ImportEngine(first).commit()
        self.assertEqual(Device.objects.filter(needs_identifying=True).count(), 1)
        placeholder = Device.objects.get(needs_identifying=True)
        self.assertTrue(placeholder.name.startswith("UNNAMED-"))
        self.assertEqual(placeholder.source, "import")

        second = self.make_batch("devices", mapping, rows)
        result, _ = ImportEngine(second).commit()
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(Device.objects.filter(needs_identifying=True).count(), 1)

    def test_free_text_connection_reference_creates_placeholders(self):
        Port.objects.create(device=self.device, label="Gi0/1")
        batch = self.make_batch(
            "connections",
            {0: "port_a", 1: "port_b", 2: "cable_label"},
            [["core-sw-01:Gi0/1", "Fortinet Gateway on Rack 1 (Port 14)", "C-101"]],
        )
        preview = ImportEngine(batch).run()
        self.assertFalse(preview.has_errors)
        self.assertEqual(preview.rows[0].action, "placeholder")
        result, _ = ImportEngine(batch).commit()
        self.assertEqual(result.created_count, 3)  # placeholder device, port and connection
        firewall = Device.objects.get(name="Fortinet Gateway")
        self.assertTrue(firewall.needs_identifying)
        self.assertTrue(Port.objects.filter(device=firewall, label="14").exists())
        self.assertTrue(Connection.objects.filter(cable_label="C-101").exists())

    def test_import_is_undoable_as_one_batch(self):
        existing = Device.objects.create(name="existing", vendor="Original", serial_number="E-1")
        batch = self.make_batch(
            "devices",
            {0: "name", 1: "serial_number", 2: "vendor"},
            [["existing", "E-1", "Changed"], ["new-device", "N-1", "New"]],
        )
        _, undo_data = ImportEngine(batch).commit()
        batch.status = ImportBatch.Status.IMPORTED
        batch.undo_data = undo_data
        batch.save(update_fields=["status", "undo_data"])
        self.assertEqual(Device.objects.get(pk=existing.pk).vendor, "Changed")
        self.assertTrue(Device.objects.filter(name="new-device").exists())

        undo_import(batch)
        self.assertFalse(Device.objects.filter(name="new-device").exists())
        self.assertEqual(Device.objects.get(pk=existing.pk).vendor, "Original")
        self.assertEqual(ImportBatch.objects.get(pk=batch.pk).status, ImportBatch.Status.UNDONE)

    def test_undo_refuses_if_placeholder_was_connected_elsewhere(self):
        batch = self.make_batch(
            "devices",
            {0: "name", 1: "notes"},
            [["manual-device", "from import"]],
        )
        _, undo_data = ImportEngine(batch).commit()
        batch.status = ImportBatch.Status.IMPORTED
        batch.undo_data = undo_data
        batch.save(update_fields=["status", "undo_data"])
        imported = Device.objects.get(name="manual-device")
        other = Device.objects.create(name="later-device")
        Port.objects.create(device=other, label="x")
        Port.objects.create(device=imported, label="y")
        Connection.objects.create(
            port_a=Port.objects.get(device=other, label="x"),
            port_b=Port.objects.get(device=imported, label="y"),
        )
        with self.assertRaises(ImportUndoError):
            undo_import(batch)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ImportWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("keeper", password="test-password-123")
        self.client.force_login(self.user)
        self.device = Device.objects.create(name="core-sw-01", device_type=Device.Type.SWITCH)

    def upload(self, filename="inventory.xlsx", rows=None):
        rows = rows or [
            ["Name", "Serial", "Vendor"],
            ["new-server", "SN-100", "Dell"],
        ]
        upload = ContentFile(workbook_bytes(rows), name=filename)
        upload.name = filename
        response = self.client.post(reverse("import_upload"), {"spreadsheet": upload})
        self.assertEqual(response.status_code, 302)
        return ImportBatch.objects.latest("created_at")

    def test_upload_to_map_preview_commit_and_undo(self):
        batch = self.upload()
        map_url = reverse("import_map", args=[batch.pk])
        self.assertContains(self.client.get(map_url), "What does each column mean?")
        response = self.client.post(
            map_url,
            {
                "sheet": "Servers",
                "target": "devices",
                "header_mode": "1",
                "map_0": "name",
                "map_1": "serial_number",
                "map_2": "vendor",
            },
        )
        self.assertRedirects(response, reverse("import_preview", args=[batch.pk]))
        preview = self.client.get(reverse("import_preview", args=[batch.pk]))
        self.assertContains(preview, "Read before you save.")
        self.assertContains(preview, "new-server")
        response = self.client.post(reverse("import_commit", args=[batch.pk]))
        self.assertRedirects(response, reverse("import_index"))
        self.assertTrue(Device.objects.filter(name="new-server", vendor="Dell", source="import").exists())
        self.assertTrue(
            ChangeLog.objects.filter(object_type="Device", object_repr="new-server").exists()
        )
        response = self.client.post(reverse("import_undo", args=[batch.pk]))
        self.assertRedirects(response, reverse("import_index"))
        self.assertFalse(Device.objects.filter(name="new-server").exists())

    def test_uploaded_file_type_is_rejected(self):
        bad = ContentFile(b"not a workbook", name="inventory.xls")
        bad.name = "inventory.xls"
        response = self.client.post(reverse("import_upload"), {"spreadsheet": bad})
        self.assertRedirects(response, reverse("import_index"))
        self.assertFalse(ImportBatch.objects.exists())

    def test_sheet_can_have_no_header(self):
        batch = self.upload(rows=[["srv-direct", "SN-5", "HP"]])
        response = self.client.post(
            reverse("import_map", args=[batch.pk]),
            {
                "sheet": "Servers",
                "target": "devices",
                "header_mode": "0",
                "map_0": "name",
                "map_1": "serial_number",
                "map_2": "vendor",
            },
        )
        self.assertRedirects(response, reverse("import_preview", args=[batch.pk]))
        preview = self.client.get(reverse("import_preview", args=[batch.pk]))
        self.assertContains(preview, "srv-direct")

    def test_duplicate_destination_fields_are_rejected(self):
        batch = self.upload()
        response = self.client.post(
            reverse("import_map", args=[batch.pk]),
            {
                "sheet": "Servers",
                "target": "devices",
                "header_mode": "1",
                "map_0": "name",
                "map_1": "name",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "only one spreadsheet column")

from unittest import TestCase
from unittest.mock import call, patch

import frappe

from vinatex.vnt_hr.doctype.vnt_attendance_confirm.data_repair import (
	delete_empty_confirmations,
)


class _FakeDatabase:
	def __init__(self, names):
		self.names = names
		self.query = None
		self.options = None

	def sql(self, query, **kwargs):
		self.query = " ".join(query.split())
		self.options = kwargs
		return self.names


class TestDeleteEmptyConfirmations(TestCase):
	def test_dry_run_reports_sorted_candidates_without_deleting(self):
		database = _FakeDatabase(["GTCC-B", "GTCC-A"])

		with (
			patch.object(frappe, "db", database),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = delete_empty_confirmations(dry_run="1")

		self.assertEqual(result["Phiếu rỗng"], ["GTCC-A", "GTCC-B"])
		self.assertEqual(result["Số phiếu rỗng"], 2)
		self.assertEqual(result["Số phiếu đã xóa"], 0)
		self.assertTrue(result["Chạy thử"])
		self.assertIn("parent.docstatus < 2", database.query)
		self.assertIn("HAVING COUNT(item.name) = 0", database.query)
		self.assertEqual(database.options, {"pluck": True})
		delete_doc.assert_not_called()

	def test_live_run_deletes_each_candidate_through_document_api(self):
		database = _FakeDatabase(["GTCC-B", "GTCC-A"])
		empty_doc = frappe._dict(docstatus=0, items=[])

		with (
			patch.object(frappe, "db", database),
			patch.object(frappe, "get_doc", return_value=empty_doc),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = delete_empty_confirmations(dry_run="0")

		self.assertEqual(result["Phiếu rỗng"], ["GTCC-A", "GTCC-B"])
		self.assertEqual(result["Số phiếu rỗng"], 2)
		self.assertEqual(result["Số phiếu đã xóa"], 2)
		self.assertFalse(result["Chạy thử"])
		self.assertEqual(
			delete_doc.call_args_list,
			[
				call(
					"VNT Attendance Confirm",
					"GTCC-A",
					ignore_permissions=True,
				),
				call(
					"VNT Attendance Confirm",
					"GTCC-B",
					ignore_permissions=True,
				),
			],
		)

	def test_live_run_reloads_with_lock_and_skips_candidate_that_gained_a_row(self):
		database = _FakeDatabase(["GTCC-CONCURRENT"])
		changed_doc = frappe._dict(
			docstatus=0,
			items=[frappe._dict(name="ROW-NEW", confirm="Đồng ý")],
		)

		with (
			patch.object(frappe, "db", database),
			patch.object(frappe, "get_doc", return_value=changed_doc) as get_doc,
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = delete_empty_confirmations(dry_run="0")

		get_doc.assert_called_once_with(
			"VNT Attendance Confirm", "GTCC-CONCURRENT", for_update=True
		)
		delete_doc.assert_not_called()
		self.assertEqual(result["Số phiếu đã xóa"], 0)
		self.assertEqual(
			result["Phiếu bỏ qua do đã thay đổi"], ["GTCC-CONCURRENT"]
		)

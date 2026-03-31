# Copyright (c) 2025, vinatex and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from vinatex.vnt_hr.doctype.vnt_meeting_room_booking.vnt_meeting_room_booking import (
	_clear_pending_approval_artifacts,
)


class TestVNTMeetingRoomBooking(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("ToDo", "Notification Log", "VNT Meeting Room Booking", "User"):
			filters = self._get_cleanup_filters(doctype)
			names = frappe.get_all(doctype, filters=filters, pluck="name")
			for name in names:
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=1)

	def test_clear_pending_approval_artifacts_closes_open_todos_and_reads_notifications(self):
		doc = self._create_booking()
		second_user = self._create_user("mrb.approver@example.com")

		open_todo_names = [
			self._create_todo(doc, "Administrator"),
			self._create_todo(doc, second_user),
		]
		other_doc_notification = self._create_notification("Administrator", "OTHER-DOC")
		target_notification_names = [
			self._create_notification("Administrator", doc.name),
			self._create_notification(second_user, doc.name),
		]

		_clear_pending_approval_artifacts(doc, extra_users=["Administrator"])

		for name in open_todo_names:
			self.assertEqual(frappe.db.get_value("ToDo", name, "status"), "Closed")

		for name in target_notification_names:
			self.assertEqual(frappe.db.get_value("Notification Log", name, "read"), 1)

		self.assertEqual(frappe.db.get_value("Notification Log", other_doc_notification, "read"), 0)

	def _create_user(self, email: str) -> str:
		if frappe.db.exists("User", email):
			return email

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Meeting",
				"last_name": "Approver",
				"enabled": 1,
				"new_password": "test",
			}
		)
		user.insert(ignore_permissions=True)
		return user.name

	def _create_booking(self):
		doc = frappe.get_doc(
			{
				"doctype": "VNT Meeting Room Booking",
				"date": "2099-12-31",
				"start_time": "8:00 AM",
				"end_time": "9:00 AM",
				"meet_online": "Không",
				"note": "UNIT-MRB test artifact",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _create_todo(self, doc, user: str) -> str:
		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": f"Approve {doc.name}",
				"allocated_to": user,
				"reference_type": doc.doctype,
				"reference_name": doc.name,
				"status": "Open",
				"priority": "Medium",
			}
		)
		todo.db_insert()
		return todo.name

	def _create_notification(self, user: str, document_name: str) -> str:
		notification = frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": f"Approve {document_name}",
				"document_type": "VNT Meeting Room Booking",
				"document_name": document_name,
				"read": 0,
			}
		)
		notification.insert(ignore_permissions=True)
		return notification.name

	def _get_cleanup_filters(self, doctype: str) -> dict:
		if doctype == "ToDo":
			booking_names = frappe.get_all(
				"VNT Meeting Room Booking",
				filters={"note": ["like", "UNIT-MRB%"]},
				pluck="name",
			)
			return {
				"reference_type": "VNT Meeting Room Booking",
				"reference_name": ["in", booking_names or [""]],
			}
		if doctype == "Notification Log":
			booking_names = frappe.get_all(
				"VNT Meeting Room Booking",
				filters={"note": ["like", "UNIT-MRB%"]},
				pluck="name",
			)
			return {
				"document_type": "VNT Meeting Room Booking",
				"document_name": ["in", booking_names or ["OTHER-DOC"]],
			}
		if doctype == "VNT Meeting Room Booking":
			return {"note": ["like", "UNIT-MRB%"]}
		return {"email": ["like", "mrb.%@example.com"]}

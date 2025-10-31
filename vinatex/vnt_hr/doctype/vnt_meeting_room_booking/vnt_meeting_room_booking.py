# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs


class VNTMeetingRoomBooking(Document):
	def validate(self):
		# kiểm tra tạo trùng lặp theo ngày và giờ họp, phiếu mới phải có start_time và end_time nằm ngoài khoảng start_time và end_time của các phiếu đã duyệt
		existing_bookings = frappe.get_all(
			"VNT Meeting Room Booking",
			filters={
				"date": self.date,
				"workflow_state": ["not in", ["Từ chối", "Hủy"]],
				"name": ["!=", self.name]  # loại trừ chính nó khi cập nhật
			},
			fields=["name", "start_time", "end_time"]
		)

		for booking in existing_bookings:
			if (self.start_time < booking.end_time and self.end_time > booking.start_time):
				frappe.throw(_("Thời gian đặt phòng bị trùng lặp với phiếu đã duyệt: {0}").format(booking.name))


	def on_update(self):
	# chuyển sang theo dõi workflow_state
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)


def _handle_state_transition(doc):
	prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)
	# lấy ra người duyệt
	approver = doc.get("approver")
	approver_user = get_employee_user_id(approver)
	if prev_state == "Mới tạo" and curr_state == "Chờ phê duyệt":
		_notify_to_approver(doc, user=approver_user)
	if prev_state == "Chờ phê duyệt" and curr_state == "Đã duyệt":
		# Đóng todo khi đã duyệt
		_check_state_to_close_todo(doc, user=approver_user)
	# gửi thông báo cho người đăng ký
	employee = doc.get("employee")
	employee_user = get_employee_user_id(employee)
	if prev_state == 'Chờ duyệt' and curr_state == 'Đã duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký phòng họp của {0} đã được lãnh đạo duyệt").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [employee_user])

	
	if prev_state == 'Chờ duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký phòng họp của {0} ngày {1} từ {2} đến {3} đã bị từ chối").format(doc.employee_name or 
			_("(không rõ)"), doc.date or _("(không rõ ngày đăng ký)"), doc.start_time or _("(không rõ thời gian bắt đầu)"), doc.end_time or _("(không rõ thời gian kết thúc)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [employee_user])


	if prev_state == 'Đã duyệt' and curr_state == 'Hủy':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký phòng họp của {0} ngày {1} từ {2} đến {3} đã bị hủy").format(doc.employee_name or
			 _("(không rõ)"), doc.date or _("(không rõ ngày đăng ký)"), doc.start_time or _("(không rõ thời gian bắt đầu)"), doc.end_time or _("(không rõ thời gian kết thúc)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [employee_user])


def _notify_to_approver(doc: Document, user: str | None):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ duyệt'."""
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đang chờ duyệt.").format(doc.get("leave_type") or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		"subject": _('Duyệt đăng ký {0} của {1}').format(doc.get("leave_type") or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
	}, [user])
	# tạo todo cho người duyệt
	ensure_todo(doc, user)


def get_employee_user_id(employee_name: str) -> str | None:
    if not employee_name:
        return None
    return frappe.db.get_value("Employee", employee_name, "user_id")


def ensure_todo(doc: Document, user: str):
	if not user:
		return
	if frappe.db.exists("ToDo", {
		"reference_type": doc.doctype,
		"reference_name": doc.name,
		"allocated_to": user,
		"status": ["!=", "Cancelled"],
	}):
		return
	description = _('Duyệt đăng ký phòng họp của {0} ngày {1} từ {2} đến {3}').format(
		doc.employee_name or _("(không rõ)"),
		doc.date or _("(không rõ ngày đăng ký)"),
		doc.start_time or _("(không rõ thời gian bắt đầu)"),
		doc.end_time or _("(không rõ thời gian kết thúc)")
	)
	new_todo =  frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = "Medium"
	new_todo.status = "Open"
	new_todo.insert(ignore_permissions=True)
	frappe.db.commit()


def _check_state_to_close_todo(doc: Document, user: str):
	"""Close open ToDos for the current approver on this document."""
	names = frappe.get_all(
	  "ToDo",
	  filters={
		  "reference_type": doc.doctype,
		  "reference_name": doc.name,
		  "allocated_to": user,
		  "status": ["!=", "Cancelled"],
	  },
	  pluck="name",
	)
	for n in names:
	  frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


def _get_prev_and_curr_workflow_state(doc: Document) -> tuple[str | None, str]:
	"""Trả về (previous_state, current_state) an toàn.
	- Ưu tiên lấy previous từ get_doc_before_save() nếu có.
	- Fallback lấy từ DB nếu chưa có trước đó (hoặc không ở on_update).
	"""
	prev_state = None
	try:
		before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
		if before:
			prev_state = (before.get("workflow_state") or "").strip()
	except Exception:
		prev_state = None
 
	if not prev_state and doc.get("name"):
		try:
			prev_state = (frappe.db.get_value(doc.doctype, doc.name, "workflow_state") or "").strip()
		except Exception:
			prev_state = None
 
	curr_state = (doc.get("workflow_state") or "").strip()
	return prev_state, curr_state


@frappe.whitelist()
def get_reports_to(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "department", as_dict=True)
	if not employee_doc:
		return
	approver = frappe.get_value("Department Approver", {"parent": employee_doc.department, "custom_level_1": True}, "approver", as_dict=True)
	if approver:
		approver_name = frappe.get_value("Employee", {"user_id": approver.approver}, "employee_name")
		return approver_name
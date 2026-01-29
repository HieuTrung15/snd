# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.desk.form.assign_to import close_all_assignments as frappe_close_assignments
from frappe.model.document import Document
from frappe.utils import formatdate, get_url_to_form
from frappe.utils.data import escape_html
from vinatex.patches.utils.rocket_chat import send_rocket_message
from vinatex.vnt_hr.doctype.vnt_office_settings.vnt_office_settings import (
	get_office_manager_employee,
	get_room_follower,
)


MEETING_ROOM_NOTIFICATION_USER_GROUP = "Office Manager"


class VNTMeetingRoomBooking(Document):
	def validate(self):
		_sync_follower_from_settings(self)
		self._validate_time_fields()
		self._validate_room_availability()

	def on_update(self):
		# chuyển sang theo dõi workflow_state
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)
		if self.workflow_state == "Đã duyệt" and self.has_value_changed("room_name"):
			_handle_room_assignment_update(self)

	def on_update_after_submit(self):
		self._validate_room_availability()
		if self.workflow_state == "Đã duyệt" and self.has_value_changed("room_name"):
			_handle_room_assignment_update(self)

	def on_cancel(self):
		_close_all_todos_for_doc(self)
		_close_all_assignments(self)


	def _validate_time_fields(self):
		start = _parse_time(self.start_time)
		end = _parse_time(self.end_time)

		if not start or not end:
			frappe.throw(_("Vui lòng chọn đầy đủ thời gian bắt đầu và kết thúc hợp lệ."))

		if start >= end:
			frappe.throw(_("Thời gian kết thúc phải muộn hơn thời gian bắt đầu."))


	def _validate_room_availability(self):
		if self.workflow_state != "Đã duyệt" and self.docstatus != 1:
			return

		if not (self.date and self.room_name):
			return

		start = _parse_time(self.start_time)
		end = _parse_time(self.end_time)

		if not start or not end:
			return

		existing_bookings = frappe.get_all(
			"VNT Meeting Room Booking",
			filters={
				"date": self.date,
				"room_name": self.room_name,
				"workflow_state": "Đã duyệt",
				"docstatus": 1,
				"name": ["!=", self.name],  # loại trừ chính nó
			},
			fields=["name", "start_time", "end_time"]
		)

		for booking in existing_bookings:
			booking_start = _parse_time(booking.start_time)
			booking_end = _parse_time(booking.end_time)

			if not booking_start or not booking_end:
				continue

			if _time_ranges_overlap(start, end, booking_start, booking_end):
				frappe.throw(_("Thời gian đặt phòng bị trùng với phiếu đã duyệt: {0}").format(booking.name))


def _handle_state_transition(doc):
	prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)
	# lấy ra người duyệt
	approver = doc.get("approver")
	approver_user = get_employee_user_id(approver)
	if curr_state == "Chờ duyệt":
		_notify_to_approver(doc, user=approver_user)
	if prev_state == "Chờ duyệt" and curr_state == "Đã duyệt":
		# Đóng todo khi đã duyệt
		_check_state_to_close_todo(doc, user=approver_user)
		_handle_room_assignment_post_approval(doc)
	# gửi thông báo cho người đăng ký
	employee = doc.get("employee")
	employee_user = get_employee_user_id(employee)
	if prev_state == 'Chờ duyệt' and curr_state == 'Đã duyệt':
		subject = _("Phiếu đăng ký phòng họp của {0} đã được duyệt").format(doc.employee_name or _("(không rõ)"))
		message = _("Phiếu ngày {0} từ {1} đến {2} đã được duyệt.").format(
			_format_date_value(doc.date, _("(không rõ ngày đăng ký)")),
			doc.start_time or _("(không rõ thời gian bắt đầu)"),
			doc.end_time or _("(không rõ thời gian kết thúc)"),
		)
		_notify_users(doc, [employee_user], subject, message)


	if prev_state == 'Chờ duyệt' and curr_state == 'Từ chối':
		date_label = _format_date_value(doc.date, _("(không rõ ngày đăng ký)"))
		subject = _("Phiếu đăng ký phòng họp của {0} ngày {1} từ {2} đến {3} đã bị từ chối").format(
			doc.employee_name or _("(không rõ)"),
			date_label,
			doc.start_time or _("(không rõ thời gian bắt đầu)"),
			doc.end_time or _("(không rõ thời gian kết thúc)"),
		)
		_notify_users(doc, [employee_user], subject, subject)
	if curr_state == 'Từ chối' and prev_state != 'Từ chối':
		_close_all_todos_for_doc(doc)
		_close_all_assignments(doc)


	if prev_state == 'Đã duyệt' and curr_state == 'Hủy':
		date_label = _format_date_value(doc.date, _("(không rõ ngày đăng ký)"))
		subject = _("Phiếu đăng ký phòng họp của {0} ngày {1} từ {2} đến {3} đã bị hủy").format(
			doc.employee_name or _("(không rõ)"),
			date_label,
			doc.start_time or _("(không rõ thời gian bắt đầu)"),
			doc.end_time or _("(không rõ thời gian kết thúc)"),
		)
		_notify_users(doc, [employee_user], subject, subject)
	if curr_state == 'Hủy' and prev_state != 'Hủy':
		_close_all_todos_for_doc(doc)
		_close_all_assignments(doc)

	# thông báo cho danh sách nhân sự
	if (prev_state == 'Chờ duyệt' and curr_state == 'Từ chối'):
		_notify_to_employee(doc, "từ chối")


def _notify_to_approver(doc: Document, user: str | None):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ duyệt'."""
	date_label = _format_date_value(doc.date, _("(không rõ ngày đăng ký)"))
	subject = _('Duyệt đăng ký phòng họp của {0} ngày {1}').format(
		doc.employee_name or _("(không rõ)"),
		date_label,
	)
	message = _('Phiếu đăng ký phòng họp của {0} ngày {1} đang chờ duyệt.').format(
		doc.employee_name or _("(không rõ)"),
		date_label,
	)
	_notify_users(doc, [user], subject, message)
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
	date_label = _format_date_value(doc.date, _("(không rõ ngày đăng ký)"))
	description = _('Duyệt đăng ký phòng họp của {0} ngày {1} từ {2} đến {3}').format(
		doc.employee_name or _("(không rõ)"),
		date_label,
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


def _notify_users(doc: Document, users, subject: str, message: str | None = None):
	if isinstance(users, (list, tuple, set)):
		target_users = {u for u in users if u}
	elif users:
		target_users = {users}
	else:
		target_users = set()

	if not target_users:
		return

	recipients = list(target_users)
	payload = {
		"type": "Alert",
		"subject": subject,
		"document_type": doc.doctype,
		"document_name": doc.name,
	}
	if message:
		payload["message"] = message

	make_notification_logs(payload, recipients)
	url = get_url_to_form(doc.doctype, doc.name)
	teams_lines = [
		"<b>🔔 Thông báo</b>",
		f"<b>{escape_html(subject)}</b>",
	]
	if message:
		teams_lines.append(escape_html(message).replace("\n", "<br>"))
	teams_lines.append(f'<a href="{escape_html(url)}">Xem chi tiết</a>')
	teams_message = "<br>".join(teams_lines)
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=recipients,
		content_type="html",
		linkify=False,
		message=teams_message,
	)
	send_rocket_message(
		to_users=recipients,
		title=":bell: Thông báo",
		message=f"*{subject}*\n{message}" if message else subject,
		link=url,
	)


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


def _handle_room_assignment_post_approval(doc: Document):
	if doc.room_name:
		_close_office_manager_todos(doc)
		_create_follower_follow_up(doc)
		_notify_room_assignment_to_requester(doc)
		_close_all_assignments(doc)
	else:
		_close_follower_todos(doc)
		_notify_office_manager_for_missing_room(doc)


def _handle_room_assignment_update(doc: Document):
	if doc.room_name:
		_close_office_manager_todos(doc)
		_create_follower_follow_up(doc)
		_notify_room_assignment_to_requester(doc)
		_close_all_assignments(doc)
	else:
		_close_follower_todos(doc)
		_notify_office_manager_for_missing_room(doc)


def _notify_office_manager_for_missing_room(doc: Document):
	users = _get_office_manager_users()
	if not users:
		return
	date_label = _format_date_value(doc.date, _("(không rõ ngày đăng ký)"))
	description = _('Cấp phòng họp cho phiếu đăng ký của {0} ngày {1} từ {2} đến {3}').format(
		doc.employee_name or _("(không rõ)"),
		date_label,
		doc.start_time or _("(không rõ thời gian bắt đầu)"),
		doc.end_time or _("(không rõ thời gian kết thúc)"),
	)
	subject =  _('Cấp phòng họp cho phiếu đăng ký của {0} ngày {1} từ {2} đến {3}').format(
		doc.employee_name or _("(không rõ)"),
		date_label,
		doc.start_time or _("(không rõ thời gian bắt đầu)"),
		doc.end_time or _("(không rõ thời gian kết thúc)"),
	)
	_notify_users(doc, users, subject, description)
	for user in users:
		_ensure_reference_todo(doc, user, description, priority="High")


def _create_follower_follow_up(doc: Document):
	follower_employee = doc.get("follower")
	follower_user = get_employee_user_id(follower_employee)
	if not follower_user:
		return
	date_label = _format_date_value(doc.date, _("(không rõ ngày đăng ký)"))
	description = _('Chuẩn bị phòng {0} cho cuộc họp của {1} ngày {2} từ {3} đến {4}').format(
		doc.room_name or _("(không rõ phòng)"),
		doc.employee_name or _("(không rõ)"),
		date_label,
		doc.start_time or _("(không rõ thời gian bắt đầu)"),
		doc.end_time or _("(không rõ thời gian kết thúc)"),
	)
	subject = _('Chuẩn bị phòng {0} cho phiếu đăng ký {1}').format(doc.room_name or _("(không rõ phòng)"), doc.name)
	_notify_users(doc, [follower_user], subject, description)
	_ensure_reference_todo(doc, follower_user, description)


def _close_office_manager_todos(doc: Document):
	users = _get_office_manager_users()
	if not users:
		return
	_close_todos_for_users(doc, users)


def _close_follower_todos(doc: Document):
	follower_employee = doc.get("follower")
	if not follower_employee:
		return
	user = get_employee_user_id(follower_employee)
	if not user:
		return
	_close_todos_for_users(doc, [user])


def _close_todos_for_users(doc: Document, users: list[str]):
	if not users:
		return
	names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"allocated_to": ["in", users],
			"status": ["in", ["Open", "Overdue"]],
		},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("ToDo", name, "status", "Closed", update_modified=False)


def _close_all_todos_for_doc(doc: Document):
	names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"status": ["in", ["Open", "Overdue"]],
		},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("ToDo", name, "status", "Closed", update_modified=False)


def _close_all_assignments(doc: Document):
	if not (doc and doc.name):
		return
	frappe_close_assignments(doc.doctype, doc.name, ignore_permissions=True)


def _ensure_reference_todo(doc: Document, user: str, description: str, priority: str = "Medium"):
	if not user:
		return
	if frappe.db.exists("ToDo", {
		"reference_type": doc.doctype,
		"reference_name": doc.name,
		"allocated_to": user,
		"status": ["in", ["Open", "Overdue"]],
	}):
		return
	new_todo = frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = priority
	new_todo.status = "Open"
	new_todo.insert(ignore_permissions=True)
	frappe.db.commit()


def _get_enabled_users_in_user_group(user_group_name: str) -> list[str]:
	if not user_group_name:
		return []
	user_ids = frappe.get_all(
		"User Group Member",
		filters={"parent": user_group_name},
		pluck="user",
	)
	if not user_ids:
		return []
	user_ids = list({user for user in user_ids if user not in {"Guest", "Administrator"}})
	if not user_ids:
		return []
	return frappe.get_all(
		"User",
		filters={
			"name": ["in", user_ids],
			"enabled": 1,
		},
		pluck="name",
	)


def _get_office_manager_users() -> list[str]:
	office_manager = get_office_manager_employee()
	if office_manager:
		user = get_employee_user_id(office_manager)
		return [user] if user else []
	return _get_enabled_users_in_user_group(MEETING_ROOM_NOTIFICATION_USER_GROUP)


def _sync_follower_from_settings(doc: Document):
	if not (doc and doc.room_name):
		return
	follower, follower_name = get_room_follower(doc.room_name)
	if not follower:
		return
	if doc.follower != follower:
		doc.follower = follower
	if follower_name and doc.follower_name != follower_name:
		doc.follower_name = follower_name


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

def _notify_to_employee(doc: Document, status: str):
	"""Gửi thông báo đến list nhân viên(list_emp) khi đơn được duyệt hoặc từ chối."""
	list_emp = doc.get("list_emp")
	if not list_emp:
		return
	for emp in list_emp:
		employee_user = get_employee_user_id(emp.employee)
		if not employee_user:
			continue
		subject = _("Phiếu đăng ký phòng họp của {0} đã {1}.").format(
			doc.employee_name or _("(không rõ)"),
			status,
		)
		message = _("Ngày {0} từ {1} đến {2}.").format(
			_format_date_value(doc.date, _("(không rõ ngày đăng ký)")),
			doc.start_time or _("(không rõ thời gian bắt đầu)"),
			doc.end_time or _("(không rõ thời gian kết thúc)"),
		)
		_notify_users(doc, [employee_user], subject, message)


def _notify_room_assignment_to_requester(doc: Document):
	"""Thông báo khi phiếu đã được chọn phòng cho người đăng ký và list nhân sự đi kèm."""
	if doc.workflow_state != "Đã duyệt" or not doc.room_name:
		return

	target_users = set()

	employee_user = get_employee_user_id(doc.get("employee"))
	if employee_user:
		target_users.add(employee_user)

	for emp in doc.get("list_emp") or []:
		emp_user = get_employee_user_id(emp.employee)
		if emp_user:
			target_users.add(emp_user)

	if not target_users:
		return

	subject = _("Phiếu đăng ký phòng họp của {0} đã được bố trí tại phòng {1}.").format(
		doc.employee_name or _("(không rõ)"),
		doc.room_name,
	)
	message = _("Ngày {0} từ {1} đến {2}.").format(
		_format_date_value(doc.date, _("(không rõ ngày đăng ký)")),
		doc.start_time or _("(không rõ thời gian bắt đầu)"),
		doc.end_time or _("(không rõ thời gian kết thúc)"),
	)
	_notify_users(doc, target_users, subject, message)


def _format_date_value(value: str | None, fallback: str) -> str:
	if not value:
		return fallback
	try:
		return formatdate(value, "dd/MM/yyyy")
	except Exception:
		return value or fallback

# fomat: HH:MM AM/PM sang HH:MM:SS or HH:MM
def _parse_time(value: str | None):
	if not value:
		return None
	value = value.strip()
	for fmt in ("%I:%M %p", "%H:%M:%S", "%H:%M"):
		try:
			return datetime.strptime(value, fmt).time()
		except ValueError:
			continue
	return None


def _time_ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
	return start_a < end_b and end_a > start_b


@frappe.whitelist()
def get_reports_to(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "department", as_dict=True)
	if not employee_doc:
		return
	approver = frappe.get_value("Department Approver", {"parent": employee_doc.department, "custom_level_1": True}, "approver", as_dict=True)
	if approver:
		approver_name = frappe.get_value("Employee", {"user_id": approver.approver}, "employee_name")
		return approver_name


@frappe.whitelist()
def get_taken_rooms(date: str | None):
	if not date:
		return []

	return frappe.get_all(
		"VNT Meeting Room Booking",
		filters={
			"date": date,
			"workflow_state": "Đã duyệt",
			"docstatus": 1,
			"room_name": ["!=", None],
		},
		fields=["date", "room_name", "start_time", "end_time", "employee","employee_name"],
		order_by="room_name asc, start_time asc"
	)

# Copyright (c) 2015,
# Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals

import json
import math
from datetime import datetime, timedelta, time
from typing import Dict, Tuple

import frappe
from frappe import _
from frappe.model.workflow import get_workflow
from frappe.query_builder import DocType
from frappe.utils import date_diff, flt, getdate, get_link_to_form, formatdate, nowdate

from frappe.model.document import Document

from dateutil.relativedelta import relativedelta
from erpnext.buying.doctype.supplier_scorecard.supplier_scorecard import daterange
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from hrms.hr.doctype.leave_application.leave_application import (
	LeaveApplication,
	get_allocation_expiry_for_cf_leaves,
	get_leave_balance_on,
	get_number_of_leave_days,
	is_lwp,
)
from hrms.hr.doctype.leave_ledger_entry.leave_ledger_entry import delete_ledger_entry
from hrms.hr.utils import get_holiday_dates_for_employee
from frappe.utils.data import get_url_to_form
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.model.workflow import get_workflow_name
from vinatex.patches.utils.rocket_chat import send_rocket_message

# from eupapp.eup_hr.doctype.xac_nhan_cham_cong.xac_nhan_cham_cong import update_event
# from eupapp.eupapp.doctype.overrides.workflow import gen_approve_channel


class AttendanceAlreadyMarkedError(frappe.ValidationError):
	pass


class VntLeaveApplication(LeaveApplication):
	LEAVE_TYPE = "Công tác"
	
	# def save(self):
	# 	super().save()
		# notify(self, self.employee_name, self.leave_approver)
			
			
	def before_submit(self):
		self.status = "Approved"


	def on_cancel(self):
		super().on_cancel()
		_check_emp_checkin_after_cancel(self)


	def on_update(self):
		# chuyển sang theo dõi workflow_state
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)


	def validate_attendance(self):
		attendance_dates = frappe.get_all(
			"Attendance",
			filters={
				"employee": self.employee,
				"attendance_date": ("between", [self.from_date, self.to_date]),
				"status": ("in", ["Work From Home"]),
				"docstatus": 1,
				"half_day_status": ("!=", "Absent"),
			},
			fields=["name", "attendance_date"],
			order_by="attendance_date",
		)
		if attendance_dates:
			frappe.throw(
				_("Attendance for employee {0} is already marked for the following dates: {1}").format(
					self.employee,
					(
						"<br><ul><li>"
						+ "</li><li>".join(
							get_link_to_form("Attendance", a.name, label=formatdate(a.attendance_date))
							for a in attendance_dates
						)
						+ "</li></ul>"
					),
				),
				AttendanceAlreadyMarkedError,
			)


	def validate(self):
		self.validate_attendance()
		super().validate()
		# kiểm tra gửi đơn nghỉ phép năm, nghỉ không hưởng lương, lao động nam nghỉ do có vợ sinh con trước bao nhiêu ngày
		if getattr(self, "leave_type", None) == 'Nghỉ phép năm' and getattr(self, "from_date", None) and getattr(self, "to_date", None):
			days_diff = date_diff(self.to_date, self.from_date) + 1  # số ngày nghỉ thực tế
			# "Nghỉ 02 ngày phải gửi đơn trước 01 ngày.
			#  Nghỉ từ 03 - 06 ngày, phải gửi đơn trước ít nhất 03 ngày.
			#  Nghỉ từ 07 ngày trở lên, phải gửi đơn trước ít nhất 14 ngày."
			days_notice = 0
			if days_diff == 2:
				days_notice = 1
			elif 3 <= days_diff <= 6:
				days_notice = 3
			elif days_diff >= 7:
				days_notice = 14
			if days_notice > 0 and date_diff(self.from_date, frappe.utils.nowdate()) < days_notice:
				frappe.msgprint(_("Đơn nghỉ phép năm {0} ngày phải gửi trước ít nhất {1} ngày. Vui lòng kiểm tra lại.").format(days_diff, days_notice), alert=True, indicator='orange')
		if getattr(self, "leave_type", None) == 'Nghỉ không hưởng lương' and getattr(self, "from_date", None) and getattr(self, "to_date", None):
			days_diff = date_diff(self.to_date, self.from_date) + 1  # số ngày nghỉ thực tế
			# "Nghỉ dưới 7 ngày báo trước ít nhất 3 ngày.
			# Nghỉ từ 7 ngày trở lên báo trước ít nhất 14 ngày."
			days_notice = 3 if days_diff < 7 else 14
			if date_diff(self.from_date, frappe.utils.nowdate()) < days_notice:
				frappe.msgprint(_("Đơn nghỉ không hưởng lương {0} ngày phải gửi trước ít nhất {1} ngày. Vui lòng kiểm tra lại.").format(days_diff, days_notice), alert=True, indicator='orange')
		if getattr(self, "leave_type", None) == 'Lao động nam nghỉ do có vợ sinh con' and getattr(self, "from_date", None) and getattr(self, "to_date", None):
			days_diff = date_diff(self.to_date, self.from_date) + 1  # số ngày nghỉ thực tế
			# "Nghỉ 02 ngày phải gửi đơn trước 01 ngày.
			# Nghỉ từ 03 - 06 ngày, phải gửi đơn trước ít nhất 03 ngày.
			# Nghỉ từ 07 ngày trở lên, phải gửi đơn trước ít nhất 14 ngày."
			days_notice = 0
			if days_diff == 2:
				days_notice = 1
			elif 3 <= days_diff <= 6:
				days_notice = 3 
			elif days_diff >= 7:
				days_notice = 14
			if days_notice > 0 and date_diff(self.from_date, frappe.utils.nowdate()) < days_notice:
				frappe.msgprint(_("Đơn nghỉ lao động nam do có vợ sinh con {0} ngày phải gửi trước ít nhất {1} ngày. Vui lòng kiểm tra lại.").format(days_diff, days_notice), alert=True, indicator='orange')


def _handle_state_transition(doc: Document):
	prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)

	# Tự động duyệt luôn nếu người duyệt 1 và 2 giống nhau, áp dụng cho văn phòng 2
	if curr_state == "Chờ lãnh đạo tập đoàn duyệt" and \
		doc.custom_approver and doc.custom_approver == doc.custom_second_approver:
		doc.workflow_state = "Đã duyệt"
		doc.db_set("workflow_state", "Đã duyệt")
		# Nếu là bước duyệt cuối, cần đảm bảo docstatus và status cũng được cập nhật
		doc.status = "Approved"
		doc.db_set("status", "Approved")
		doc.db_set("docstatus", 1)
		curr_state = "Đã duyệt"

	leave_type = doc.get("leave_type")
	employee_user = doc.get("employee")
	approver_user = get_employee_user_id(employee_user)
	url = get_url_to_form(doc.doctype, doc.name)

	if curr_state == "Chờ lãnh đạo duyệt" and prev_state == "Mới tạo":
		_notify_to_approver(doc)
	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		_notify_to_approver_2(doc)

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt' or \
		prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Đã duyệt':
		_check_state_to_close_todo(doc, doc.get("custom_approver"))
	
	if curr_state == 'Từ chối':
		_check_state_to_close_todo(doc, doc.get("custom_approver"))
		_check_state_to_close_todo(doc, doc.get("custom_second_approver"))

	if curr_state == "Chờ lãnh đạo tập đoàn duyệt" and prev_state == "Mới tạo":
		_notify_to_approver_2(doc)

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Đã duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký {0} của {1} đã được duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đã được duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=approver_user,
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký {0} của {1} đã được duyệt <br>"
				"<a href=\"{2}\">Xem chi tiết</a>"
			).format(
				leave_type or _("(không rõ)"), 
				doc.employee_name or _("(không rõ)"),
				url
			),
		)


	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký {0} của {1} đang chờ duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đang chờ duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=approver_user,
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký {0} của {1} đang chờ duyệt <br>"
				"<a href=\"{2}\">Xem chi tiết</a>"
			).format(
				leave_type or _("(không rõ)"), 
				doc.employee_name or _("(không rõ)"),
				url
			),
		)

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Đã duyệt':
		_check_state_to_close_todo(doc, doc.get("custom_second_approver"))
		# chỉ gửi thông báo đến lđ cấp 2
		_send_to_noti_2(doc)
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký {0} của {1} đã được duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đã được duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=approver_user,
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký {0} của {1} đã được duyệt <br>"
				"<a href=\"{2}\">Xem chi tiết</a>"
			).format(
				leave_type or _("(không rõ)"), 
				doc.employee_name or _("(không rõ)"),
				url
			),
		)

	# gửi thông báo cho giám đốc nếu lãnh đạo cấp trung nghỉ phép
	if doc.custom_designation_group == "Lãnh đạo cấp trung" and curr_state == 'Đã duyệt':
		_notify_to_general_manager(doc)

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đã bị từ chối vì lý do: {2}.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)"), doc.custom_reject_reason or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		}, [approver_user])
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=approver_user,
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký {0} của {1} đã bị từ chối vì lý do: {2}. <br>"
				"<a href=\"{3}\">Xem chi tiết</a>"
			).format(
				leave_type or _("(không rõ)"), 
				doc.employee_name or _("(không rõ)"),
				doc.custom_reject_reason or _("(không rõ)"),
				url
			),
		)

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đã bị từ chối vì lý do: {2}.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)"), doc.custom_reject_reason or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đã bị từ chối vì lý do: {2}.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)"), doc.custom_reject_reason or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=approver_user,
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký {0} của {1} đã bị từ chối vì lý do: {2}. <br>"
				"<a href=\"{3}\">Xem chi tiết</a>"
			).format(
				leave_type or _("(không rõ)"), 
				doc.employee_name or _("(không rõ)"),
				doc.custom_reject_reason or _("(không rõ)"),
				url
			),
		)


def _send_to_noti_2(doc: Document):
	receivers = _receiver_noti_2_list(doc.department)
	if not receivers:
		return

	employee_name = doc.employee_name or _("(không rõ)")
	leave_type = doc.leave_type or _("(không rõ)")
	from_date = formatdate(doc.from_date, "dd-MM-yyyy") if doc.from_date else _("(không rõ)")
	to_date = formatdate(doc.to_date, "dd-MM-yyyy") if doc.to_date else _("(không rõ)")
	subject = _("{0} đã được duyệt {1} {2} {3}").format(employee_name, leave_type, from_date, to_date)
	url = get_url_to_form(doc.doctype, doc.name)
	make_notification_logs({
		"type": "Alert",
		"subject": subject,
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, receivers)
	send_rocket_message(
		to_users=receivers,
		title=":bell: Thông báo",
		message=subject,
		# link=get_url_to_form(doc.doctype, doc.name)
	)
	html_message = _("🔔 {0}<br><a href=\"{1}\">Xem chi tiết</a>").format(
		subject,
		url,
	)
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=receivers,
		content_type="html",
		linkify=False,
		message=html_message,
	)


# lấy ra danh sách người nhận thông báo cấp 2, ở trạng thái đã duyệt
def _receiver_noti_2_list(department: str | None = None) -> list[str]:
	"""Lấy danh sách approver (user) được check custom_receiver_noti_2 trong Department Approver."""
	if not department:
		return []

	receivers = frappe.get_all(
		"Department Approver",
		filters={
			"parent": department,
			"parentfield": "leave_approvers",
			"parenttype": "Department",
			"custom_receiver_noti_2": 1,
		},
		pluck="approver",
		order_by="idx asc",
	)

	return [user for user in dict.fromkeys(receivers or []) if user]


def _notify_to_general_manager(doc: Document):
	user_group_name = "Gửi thông báo cho tổng giám đốc"
	user_list = frappe.get_all(
		"User Group Member",
		filters={"parent": user_group_name},
		pluck="user",
	)
	make_notification_logs({
		"type": "Alert",
		"subject": _("{0} đã được duyệt đăng ký nghỉ phép từ {1} đến {2}").format(
			doc.employee_name,
			formatdate(doc.from_date, "dd-MM-yyyy"),
			formatdate(doc.to_date, "dd-MM-yyyy"),
		),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, user_list)
	send_rocket_message(
		to_users=user_list,
		title=":bell: Thông báo",
		message=_("{0} đã được duyệt đăng ký nghỉ phép từ {1} đến {2}").format(
			doc.employee_name,
			formatdate(doc.from_date, "dd-MM-yyyy"),
			formatdate(doc.to_date, "dd-MM-yyyy"),
		),
		link=get_url_to_form(doc.doctype, doc.name)
	)
	url = get_url_to_form(doc.doctype, doc.name)
	# frappe.enqueue(
	# 	"vinatex.integrations.teams_graph.notify_user",
	# 	queue="short",
	# 	timeout=30,
	# 	is_async=True,
	# 	upn_or_email=user_list,
	# 	content_type="html",
	# 	linkify=False,
	# 	message=_(
	# 		"🔔 {0} đã được duyệt đăng ký nghỉ phép từ {1} đến {2} <br>"
	# 		"<a href=\"{3}\">Xem chi tiết</a>"
	# 	).format(
	# 		doc.employee_name,
	# 		formatdate(doc.from_date, "dd-MM-yyyy"),
	# 		formatdate(doc.to_date, "dd-MM-yyyy"),
	# 		url
	# 	),
	# )


def _check_emp_checkin_after_cancel(doc: Document):
	"""kiểm tra nếu nhân viên đã có dữ liệu Employee Checkin trong khoảng nghỉ phép đã duyệt thì tạo attendance tương ứng."""
	# kiểm tra dữ liệu Attendance
	from frappe.utils import getdate
	attendance_records = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"attendance_date": ("between", [doc.from_date, doc.to_date]),
			"docstatus": 1,
			"status": ("in", ["Present", "Work From Home"]),
		},
		fields=["name", "attendance_date", "status"],
		order_by="attendance_date",
	)
	if attendance_records:
		return  # đã có attendance thì không tạo nữa
	# kiểm tra dữ liệu Employee Checkin
	employee_checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": doc.employee,
			"time": ("between", [str(doc.from_date) + " 00:00:00", str(doc.to_date) + " 23:59:59"]),
		},
		fields=["name", "time"],
		order_by="time",
	)
	if not employee_checkins:
		return  # không có dữ liệu checkin thì không làm gì
	# tạo attendance cho các ngày có checkin
	attendance_dates = set()
	for checkin in employee_checkins:
		checkin_date = getdate(checkin.time)
		attendance_dates.add(checkin_date)
	for att_date in attendance_dates:
		new_attendance = frappe.new_doc("Attendance")
		new_attendance.employee = doc.employee
		new_attendance.employee_name = doc.employee_name
		new_attendance.company = doc.company
		new_attendance.department = doc.department
		new_attendance.attendance_date = att_date
		new_attendance.status = "Present"
		new_attendance.docstatus = 1
		new_attendance.insert(ignore_permissions=True)
		frappe.db.commit()


def _notify_to_approver(doc: Document):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo duyệt'."""
	leave_type = doc.get("leave_type")
	approver_emp = doc.get("custom_approver")
	approver = get_employee_user_id(approver_emp)
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		"subject": _('Duyệt đăng ký {0} của {1}').format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
	}, [approver])
	send_rocket_message(
        to_users=approver,
        title=":bell: Thông báo",
        message=_("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
        link=get_url_to_form(doc.doctype, doc.name)
    )
	url = get_url_to_form(doc.doctype, doc.name)
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=approver,
		content_type="html",
		linkify=False,
		message=_(
			"🔔 Phiếu đăng ký {0} của {1} đang chờ duyệt <br>"
			"<a href=\"{2}\">Xem chi tiết</a>"
		).format(
			leave_type or _("(không rõ)"), 
			doc.employee_name or _("(không rõ)"),
			url
		),
	)
	# tạo todo cho người duyệt
	ensure_todo(doc, approver)


def get_employee_user_id(employee_name: str) -> str | None:
	if not employee_name:
		return None
	return frappe.db.get_value("Employee", employee_name, "user_id")


def _notify_to_approver_2(doc: Document):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo duyệt'."""
	leave_type = doc.get("leave_type")
	approver_emp = doc.get("custom_second_approver")
	approver = get_employee_user_id(approver_emp)
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đang chờ duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		# "subject": _('Duyệt đăng ký {0} của {1}').format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
	}, [approver])
	send_rocket_message(
        to_users=approver,
        title=":bell: Thông báo",
        message=_("Phiếu đăng ký {0} của {1} đang chờ duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
        link=get_url_to_form(doc.doctype, doc.name)
    )
	url = get_url_to_form(doc.doctype, doc.name)
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=approver,
		content_type="html",
		linkify=False,
		message=_(
			"🔔 Phiếu đăng ký {0} của {1} đang chờ duyệt <br>"
			"<a href=\"{2}\">Xem chi tiết</a>"
		).format(
			leave_type or _("(không rõ)"), 
			doc.employee_name or _("(không rõ)"),
			url
		),
	)
	# tạo todo cho người duyệt
	ensure_todo(doc, approver)


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
	leave_type = doc.get("leave_type") or _("(chưa xác định loại nghỉ phép)")
	employee = doc.get("employee_name") or _("(không rõ người tạo)")
	from_date = doc.get("from_date") or _("(không rõ ngày bắt đầu)")
	to_date = doc.get("to_date") or _("(không rõ ngày kết thúc)")
	total_leave_days = doc.get("total_leave_days") or _("(không rõ số ngày nghỉ)")
	description = _('Duyệt đăng ký {0} của {1}').format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)"))
	new_todo =  frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = "Medium"
	new_todo.status = "Open"
	new_todo.save(ignore_permissions=True)
	frappe.db.commit()


def _check_state_to_close_todo(doc: Document, user: str):
	"""Close open ToDos for the current approver on this document."""
	approver = get_employee_user_id(user)
	names = frappe.get_all(
	  "ToDo",
	  filters={
		  "reference_type": doc.doctype,
		  "reference_name": doc.name,
		  "allocated_to": approver,
		  "status": ["!=", "Cancelled"],
	  },
	  pluck="name",
	)
	for n in names:
	  frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


@frappe.whitelist()
def get_leave_approver_from_employee(employee: str):
	if not employee:
		return ""

	employee_doc = frappe.get_value(
		"Employee",
		employee,
		["name", "employee_name", "department", "user_id"],
		as_dict=True,
	)
	if not employee_doc:
		return ""

	if employee_doc.user_id:
		roles = frappe.get_roles(employee_doc.user_id)
		if "Leave Approver L1" in roles or "Leave Approver L2" in roles:
			return employee_doc.name, employee_doc.employee_name

	approver_users = frappe.get_all(
		"Department Approver",
		filters={"parent": employee_doc.department, "custom_level_1": True},
		pluck="approver",
	) or []
	# Nếu user của nhân viên nằm trong danh sách approver thì trả đúng người đó
	if employee_doc.user_id in approver_users:
		return employee_doc.name, employee_doc.employee_name
	target_user = approver_users[0] if approver_users else None
	if target_user:
		approver_emp = frappe.get_value(
			"Employee",
			{"user_id": target_user},
			["name", "employee_name"],
			as_dict=True,
		)
		if approver_emp:
			return [approver_emp.get("name"), approver_emp.get("employee_name")]

@frappe.whitelist()
def get_leave_approver(employee: str):
	# lấy approver trên Employee trước
	emp = frappe.db.get_value("Employee", employee, ["reports_to", "user_id"], as_dict=True)
	if not emp.reports_to:
		approver = emp.user_id
	if emp.reports_to:
		report_to = frappe.db.get_value("Employee", emp.reports_to, ["user_id"], as_dict=True)
		if not report_to.user_id:
			frappe.throw("Chưa có người duyệt cho nhân viên này.Cần cập nhật trong Employee.")
		approver = report_to.user_id
	return approver


@frappe.whitelist()
def get_leave_approver_level_2(employee: str):
	# lấy approver trên Employee trước
	emp = frappe.db.get_value("Employee", employee, ["leave_approver", "department"], as_dict=True)
	if not emp:
		return None
	# lấy ra người duyệt cấp 2 của emp theo department
	if emp:
		approver = frappe.db.get_value(
			"Department Approver",
			{
				"parent": emp.department,
				"parentfield": "leave_approvers",
				"custom_level_2": 1,      
			},
			"approver",
		)
		if not approver:
			employee_name = frappe.db.get_value("Employee", employee,"employee_name", as_dict=True)
			return {"employee": employee, "employee_name": employee_name.employee_name}
		emp_id = frappe.db.get_value("Employee", {"user_id": approver}, ["name", "employee_name"], as_dict=True)
		return emp_id
	return

@frappe.whitelist()
def get_leave_details_with_year(employee, date, to_date=None):
	"""
	Hiển thị dashboard phép năm. 
	Quy tắc: 
	- Tính toán taken/pending dựa trên năm thực tế (Calendar split).
	- Nếu nghỉ trong Q1 (trước 31/03), ưu tiên trừ phép tồn của năm trước.
	"""
	from frappe.utils import cint, flt, getdate, nowdate
	
	from_dt, to_dt = getdate(date), getdate(to_date or date)
	precision = cint(frappe.db.get_single_value("System Settings", "float_precision")) or 2
	today = getdate(nowdate())

	# 1. Xác định các năm cần hiển thị
	years = list(range(from_dt.year, to_dt.year + 1))
	if from_dt.year == to_dt.year and to_dt <= getdate(f"{to_dt.year}-03-31"):
		years.append(from_dt.year - 1)
	years = sorted(list(set(years)))

	# 2. Chuẩn bị phạm vi tính toán (bao gồm năm liền trước để tính carry-forward)
	calc_years = sorted(list(set(years + [min(years) - 1])))

	# 3. Lấy dữ liệu Allocation cho tất cả các năm tính toán
	allocations = {} # {year: {total, taken, pending, ...}}
	for y in calc_years:
		alloc = frappe.db.get_value("Leave Allocation", 
			{"employee": employee, "leave_type": "Nghỉ phép năm", "docstatus": 1, 
			 "from_date": [">=", f"{y}-01-01"], "to_date": ["<=", f"{y}-12-31"]}, 
			["total_leaves_allocated"], as_dict=True)
		if alloc:
			allocations[y] = {
				"total": flt(alloc.total_leaves_allocated, precision),
				"taken": 0.0,
				"pending": 0.0,
			}
		else:
			allocations[y] = {"total": 0.0, "taken": 0.0, "pending": 0.0}

	# 4. Lấy dữ liệu Applications và chia bộ theo năm + Q1
	applications = frappe.get_all("Leave Application",
		filters={"employee": employee, "leave_type": "Nghỉ phép năm", "docstatus": ["in", [1, 0]], "status": ["in", ["Approved", "Open"]]},
		fields=["name", "from_date", "to_date", "total_leave_days", "docstatus", "status", "half_day", "half_day_date"])

	raw_usage = {y: {"taken": 0.0, "pending": 0.0, "q1_taken": 0.0, "q1_pending": 0.0} for y in calc_years}

	for app in applications:
		start, end = getdate(app.from_date), getdate(app.to_date)
		# Duyệt qua các năm liên quan đến đơn nghỉ này
		for y in range(start.year, end.year + 1):
			if y not in raw_usage: continue # Chỉ quan tâm năm trong calc_years (hoặc mở rộng calc_years nếu cần, nhưng thường dashboard chỉ xem range hiện tại)
			
			# Range thực tế trong năm y
			y_start = max(start, getdate(f"{y}-01-01"))
			y_end = min(end, getdate(f"{y}-12-31"))
			days = flt(get_number_of_leave_days(employee, "Nghỉ phép năm", y_start, y_end, app.half_day, app.half_day_date))
			
			# Check Q1 logic (trước 31/03)
			q1_end = getdate(f"{y}-03-31")
			q1_days = 0.0
			if y_start <= q1_end:
				# Giao của [y_start, y_end] và [y_start, q1_end]
				real_q1_end = min(y_end, q1_end)
				q1_days = flt(get_number_of_leave_days(employee, "Nghỉ phép năm", y_start, real_q1_end, app.half_day, app.half_day_date))

			if app.docstatus == 1:
				raw_usage[y]["taken"] += days
				raw_usage[y]["q1_taken"] += q1_days
			elif app.status == "Open":
				raw_usage[y]["pending"] += days
				raw_usage[y]["q1_pending"] += q1_days

	# 5. Phân bổ Usage (Rollover logic)
	# Duyệt từ năm nhỏ nhất lên. Nếu năm Y có ngày Q1, thử charge vào năm Y-1
	final_usage = {y: {"taken": 0.0, "pending": 0.0} for y in calc_years}
	
	for y in calc_years:
		# Lấy raw usage của năm nay
		curr_taken = raw_usage[y]["taken"]
		curr_pending = raw_usage[y]["pending"]
		
		# Nhận usage từ phân bổ
		final_usage[y]["taken"] += curr_taken
		final_usage[y]["pending"] += curr_pending

		# Thử đẩy Q1 usage của năm sau (y+1) về năm nay (y) nếu năm nay còn dư
		next_y = y + 1
		if next_y in raw_usage and allocations[y]["total"] > 0:
			# Số dư năm nay (chỉ tính allocations - usage đã được charge vào năm nay)
			# Lưu ý: Usage năm nay đã bao gồm các khoản từ năm trước đẩy sang (nếu logic đệ quy), 
			# nhưng ở đây ta duyệt xuôi, y-1 đã xử lý xong.
			
			used_so_far = final_usage[y]["taken"] + final_usage[y]["pending"]
			remaining_y = max(0.0, allocations[y]["total"] - used_so_far)
			
			if remaining_y > 0:
				# Q1 của năm sau
				q1_next_taken = raw_usage[next_y]["q1_taken"]
				q1_next_pending = raw_usage[next_y]["q1_pending"]
				
				# Ưu tiên cover taken trước
				cover_taken = min(remaining_y, q1_next_taken)
				remaining_y -= cover_taken
				
				cover_pending = min(remaining_y, q1_next_pending)
				remaining_y -= cover_pending
				
				# Chuyển số liệu:
				# Giảm ở năm sau (next_y) -> Vì raw_usage là const trong loop, ta trừ trong final_usage
				final_usage[next_y]["taken"] -= cover_taken
				final_usage[next_y]["pending"] -= cover_pending
				
				# Tăng ở năm nay (y)
				final_usage[y]["taken"] += cover_taken
				final_usage[y]["pending"] += cover_pending

	# 6. Build kết quả trả về (chỉ cho những năm requested `years`)
	leave_allocation = {}
	for y in years:
		# Có thể alloc ko tồn tại trong DB, nhưng ta vẫn hiển thị nếu logic yêu cầu (thường là 0)
		total = allocations[y]["total"]
		taken = final_usage[y]["taken"]
		pending = final_usage[y]["pending"]
		
		# Tính Expired
		expired = 0.0
		# Nếu là năm cũ (< năm nay), và hiện tại đã qua 31/03 năm nay -> Hết hạn
		# Hoặc chính xác hơn: Phép năm Y hết hạn vào 31/03/Y+1.
		expiry_date = getdate(f"{y+1}-03-31")
		if today > expiry_date:
			remaining = max(0.0, total - taken - pending)
			expired = remaining # Toàn bộ số dư còn lại coi như mất
		
		remaining_leaves = max(0.0, total - taken - pending - expired)
		
		if total > 0 or taken > 0 or pending > 0: # Chỉ hiển thị nếu có dữ liệu
			leave_allocation[f"Nghỉ phép năm ({y})"] = {
				"total_leaves": total,
				"expired_leaves": expired,
				"leaves_taken": taken,
				"leaves_pending_approval": pending,
				"remaining_leaves": remaining_leaves,
			}

	# Các loại nghỉ khác (Giữ nguyên logic cũ)
	others = frappe.get_all("Leave Allocation",
		filters={"employee": employee, "leave_type": ["!=", "Nghỉ phép năm"], "docstatus": 1,
				 "from_date": ["<=", str(to_dt)], "to_date": [">=", str(from_dt)]},
		fields=["leave_type", "total_leaves_allocated", "from_date", "to_date"], group_by="leave_type")
	
	for o in others:
		lt = o.leave_type
		taken = flt(frappe.db.get_value("Leave Application", {"employee": employee, "leave_type": lt, "docstatus": 1}, "sum(total_leave_days)"))
		pending = flt(frappe.db.get_value("Leave Application", {"employee": employee, "leave_type": lt, "status": "Open"}, "sum(total_leave_days)"))
		total = flt(o.total_leaves_allocated, precision)
		leave_allocation[lt] = {
			"total_leaves": total, "expired_leaves": 0, "leaves_taken": taken,
			"leaves_pending_approval": pending, "remaining_leaves": max(0, total - taken - pending),
		}
	
	return {"leave_allocation": leave_allocation, "leave_approver": get_leave_approver(employee), "lwps": frappe.get_list("Leave Type", filters={"is_lwp": 1}, pluck="name")}


def _get_total_annual_leave_balance(employee, from_date, to_date=None):
	"""
	Tính tổng phép năm khả dụng cho dải ngày [from_date, to_date].
	"""
	details = get_leave_details_with_year(employee, from_date, to_date)
	alloc_data = details.get("leave_allocation", {})
	# Trả về tổng số dư của các năm đang hiển thị
	return sum(flt(v.get("remaining_leaves", 0)) for v in alloc_data.values())

@frappe.whitelist()
def get_leave_type(
	from_date=None,
	to_date=None,
	half_day=None,
	half_day_date=None,
	leave_balance=None,
	extra_number=None,
	total_leave_days=None,
	leave_type=None,
	employee=None,
	status=None,
	leave_type_extra=None,
):
	"""
	Tách đơn nghỉ phép thành các khối (blocks) dựa trên số dư từng năm.
	Quy tắc: Ngày năm nào dùng phép năm đó trước. Hết phép năm đó mới dùng phép năm trước (nếu trong Q1).
	"""
	if not (from_date and to_date and employee and leave_type):
		return []

	from_dt, to_dt = getdate(from_date), getdate(to_date)
	leave_type_extra = leave_type_extra or "Nghỉ không hưởng lương"
	
	# 1. Lấy thông tin số dư thực tế từng năm
	details = get_leave_details_with_year(employee, from_dt, to_dt)
	alloc_data = details.get("leave_allocation", {})
	balances = {k: flt(v.get("remaining_leaves", 0)) for k, v in alloc_data.items()}
	
	# 2. Duyệt từng ngày làm việc và phân bổ
	day_results = []
	curr = from_dt
	while curr <= to_dt:
		qty = flt(get_number_of_leave_days(employee, leave_type, curr, curr, half_day, half_day_date))
		if qty > 0:
			needed = qty
			year = curr.year
			if leave_type == "Nghỉ phép năm":
				curr_key = f"Nghỉ phép năm ({year})"
				prev_key = f"Nghỉ phép năm ({year-1})"
				
				# BƯỚC 1: Dùng phép của đúng năm đó trước
				if balances.get(curr_key, 0) > 0:
					taken = min(needed, balances[curr_key])
					day_results.append({"dt": curr, "type": leave_type, "qty": taken})
					balances[curr_key] -= taken
					needed -= taken
				
				# BƯỚC 2: Nếu hết phép năm nay, dùng phép năm trước (nếu là Q1)
				if needed > 0 and curr.month <= 3 and balances.get(prev_key, 0) > 0:
					taken = min(needed, balances[prev_key])
					day_results.append({"dt": curr, "type": leave_type, "qty": taken})
					balances[prev_key] -= taken
					needed -= taken
			else:
				if balances.get(leave_type, 0) > 0:
					taken = min(needed, balances[leave_type])
					day_results.append({"dt": curr, "type": leave_type, "qty": taken})
					balances[leave_type] -= taken
					needed -= taken
			
			# BƯỚC 3: Còn dư thì là nghỉ bổ sung
			if needed > 0:
				day_results.append({"dt": curr, "type": leave_type_extra, "qty": needed})
				
		curr += timedelta(days=1)

	# 3. Gom nhóm blocks (giữ nguyên logic cũ)
	if not day_results: return []
	blocks = []
	first = day_results[0]
	current_block = {"from_date": first["dt"], "to_date": first["dt"], "leave_type": first["type"], "total_days": first["qty"], "half_day_date": first["dt"] if not float(first["qty"]).is_integer() else None}
	for i in range(1, len(day_results)):
		res = day_results[i]
		if res["type"] == current_block["leave_type"]:
			current_block["to_date"] = res["dt"]
			current_block["total_days"] += res["qty"]
			if not current_block["half_day_date"] and not float(res["qty"]).is_integer(): current_block["half_day_date"] = res["dt"]
		else:
			blocks.append(current_block)
			current_block = {"from_date": res["dt"], "to_date": res["dt"], "leave_type": res["type"], "total_days": res["qty"], "half_day_date": res["dt"] if not float(res["qty"]).is_integer() else None}
	blocks.append(current_block)

	return [{"from_date": b["from_date"], "to_date": b["to_date"], "leave_type": b["leave_type"], "total_days": b["total_days"], "half_day": 1 if b["half_day_date"] else 0, "half_day_date": b["half_day_date"] or ""} for b in blocks]

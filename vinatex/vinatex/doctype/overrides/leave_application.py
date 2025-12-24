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
from frappe.utils import date_diff, flt, getdate, get_link_to_form, formatdate
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
			"subject": _("Phiếu đăng ký {0} của {1} đã được lãnh đạo duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đã được lãnh đạo duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)

		# frappe.enqueue(
		# 	"vinatex.integrations.teams_graph.notify_user",
		# 	queue="short",
		# 	timeout=30,
		# 	is_async=True,
		# 	upn_or_email=approver_user,
		# 	content_type="html",
		# 	linkify=False,
		# 	message=_(
		# 		"🔔 Phiếu đăng ký {0} của {1} đã được lãnh đạo duyệt <br>"
		# 		"<a href=\"{2}\">Xem chi tiết</a>"
		# 	).format(
		# 		leave_type or _("(không rõ)"), 
		# 		doc.employee_name or _("(không rõ)"),
		# 		url
		# 	),
		# )


	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo tập đoàn duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo tập đoàn duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		# frappe.enqueue(
		# 	"vinatex.integrations.teams_graph.notify_user",
		# 	queue="short",
		# 	timeout=30,
		# 	is_async=True,
		# 	upn_or_email=approver_user,
		# 	content_type="html",
		# 	linkify=False,
		# 	message=_(
		# 		"🔔 Phiếu đăng ký {0} của {1} đang chờ lãnh đạo tập đoàn duyệt <br>"
		# 		"<a href=\"{2}\">Xem chi tiết</a>"
		# 	).format(
		# 		leave_type or _("(không rõ)"), 
		# 		doc.employee_name or _("(không rõ)"),
		# 		url
		# 	),
		# )

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Đã duyệt':
		_check_state_to_close_todo(doc, doc.get("custom_second_approver"))
		# chỉ gửi thông báo đến lđ cấp 2
		_send_to_noti_2(doc)
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký {0} của {1} đã được lãnh đạo tập đoàn duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đã được lãnh đạo tập đoàn duyệt").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		# frappe.enqueue(
		# 	"vinatex.integrations.teams_graph.notify_user",
		# 	queue="short",
		# 	timeout=30,
		# 	is_async=True,
		# 	upn_or_email=approver_user,
		# 	content_type="html",
		# 	linkify=False,
		# 	message=_(
		# 		"🔔 Phiếu đăng ký {0} của {1} đã được lãnh đạo tập đoàn duyệt <br>"
		# 		"<a href=\"{2}\">Xem chi tiết</a>"
		# 	).format(
		# 		leave_type or _("(không rõ)"), 
		# 		doc.employee_name or _("(không rõ)"),
		# 		url
		# 	),
		# )

	# gửi thông báo cho giám đốc nếu lãnh đạo cấp trung nghỉ phép
	if doc.custom_designation_group == "Lãnh đạo cấp trung" and curr_state == 'Đã duyệt':
		_notify_to_general_manager(doc)

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đã bị lãnh đạo từ chối.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đã bị lãnh đạo từ chối.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		# frappe.enqueue(
		# 	"vinatex.integrations.teams_graph.notify_user",
		# 	queue="short",
		# 	timeout=30,
		# 	is_async=True,
		# 	upn_or_email=approver_user,
		# 	content_type="html",
		# 	linkify=False,
		# 	message=_(
		# 		"🔔 Phiếu đăng ký {0} của {1} đã bị lãnh đạo từ chối <br>"
		# 		"<a href=\"{2}\">Xem chi tiết</a>"
		# 	).format(
		# 		leave_type or _("(không rõ)"), 
		# 		doc.employee_name or _("(không rõ)"),
		# 		url
		# 	),
		# )

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đã bị lãnh đạo tập đoàn từ chối.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký {0} của {1} đã bị lãnh đạo tập đoàn từ chối.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		# frappe.enqueue(
		# 	"vinatex.integrations.teams_graph.notify_user",
		# 	queue="short",
		# 	timeout=30,
		# 	is_async=True,
		# 	upn_or_email=approver_user,
		# 	content_type="html",
		# 	linkify=False,
		# 	message=_(
		# 		"🔔 Phiếu đăng ký {0} của {1} đã bị lãnh đạo tập đoàn từ chối <br>"
		# 		"<a href=\"{2}\">Xem chi tiết</a>"
		# 	).format(
		# 		leave_type or _("(không rõ)"), 
		# 		doc.employee_name or _("(không rõ)"),
		# 		url
		# 	),
		# )


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
	# html_message = _("🔔 {0}<br><a href=\"{1}\">Xem chi tiết</a>").format(
	# 	subject,
	# 	url,
	# )
	# frappe.enqueue(
	# 	"vinatex.integrations.teams_graph.notify_user",
	# 	queue="short",
	# 	timeout=30,
	# 	is_async=True,
	# 	upn_or_email=receivers,
	# 	content_type="html",
	# 	linkify=False,
	# 	message=html_message,
	# )


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
	# url = get_url_to_form(doc.doctype, doc.name)
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
	# url = get_url_to_form(doc.doctype, doc.name)
	# frappe.enqueue(
	# 	"vinatex.integrations.teams_graph.notify_user",
	# 	queue="short",
	# 	timeout=30,
	# 	is_async=True,
	# 	upn_or_email=approver,
	# 	content_type="html",
	# 	linkify=False,
	# 	message=_(
	# 		"🔔 Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt <br>"
	# 		"<a href=\"{2}\">Xem chi tiết</a>"
	# 	).format(
	# 		leave_type or _("(không rõ)"), 
	# 		doc.employee_name or _("(không rõ)"),
	# 		url
	# 	),
	# )
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
		"subject": _("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		# "subject": _('Duyệt đăng ký {0} của {1}').format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
	}, [approver])
	send_rocket_message(
        to_users=approver,
        title=":bell: Thông báo",
        message=_("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
        link=get_url_to_form(doc.doctype, doc.name)
    )
	# url = get_url_to_form(doc.doctype, doc.name)
	# frappe.enqueue(
	# 	"vinatex.integrations.teams_graph.notify_user",
	# 	queue="short",
	# 	timeout=30,
	# 	is_async=True,
	# 	upn_or_email=approver,
	# 	content_type="html",
	# 	linkify=False,
	# 	message=_(
	# 		"🔔 Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt <br>"
	# 		"<a href=\"{2}\">Xem chi tiết</a>"
	# 	).format(
	# 		leave_type or _("(không rõ)"), 
	# 		doc.employee_name or _("(không rõ)"),
	# 		url
	# 	),
	# )
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
	"""Split leave into paid/unpaid parts when annual leave is insufficient."""
	vals = []
	if not (from_date and to_date and employee and leave_type):
		return vals

	from_date = getdate(from_date)
	to_date = getdate(to_date)

	holidays = get_holiday_dates_for_employee(employee, from_date, to_date)
	if half_day_date:
		half_day_date = getdate(half_day_date)
		if half_day_date in holidays:
			frappe.throw(_("Can not set half day date on holiday"))

	extra_number = float(extra_number or 0)
	total_leave_days = float(
		get_number_of_leave_days(
			employee, leave_type, from_date, to_date, half_day, half_day_date
		)
	)

	if not is_lwp(leave_type):
		leave_balance_data = get_leave_balance_on(
			employee,
			leave_type,
			from_date,
			to_date,
			consider_all_leaves_in_the_allocation_period=True,
			for_consumption=True,
		)
		leave_balance = flt(max(0, leave_balance_data.get("leave_balance") or 0))
		extra_number = max(total_leave_days - leave_balance, 0)
		leave_balance_for_consumption = leave_balance_data.get(
			"leave_balance_for_consumption"
		)

		if (
			status != "Rejected"
			and leave_type == "Nghỉ phép năm"
			and (not leave_balance_for_consumption or leave_balance_for_consumption < total_leave_days)
		):
			# np_to_date: last date covered by paid annual leave
			np_to_date = from_date + relativedelta(days=math.ceil(leave_balance - 1))
			np_no_of_holidays = len(
				get_holiday_dates_for_employee(employee, from_date, np_to_date)
			)
			nkl_no_of_holidays = len(
				get_holiday_dates_for_employee(
					employee, np_to_date + relativedelta(days=np_no_of_holidays + 1), to_date
				)
			)

			# Part 1: paid annual leave
			if leave_balance > 0:
				vals.append(
					{
						"from_date": from_date,
						"to_date": np_to_date + relativedelta(days=np_no_of_holidays),
						"leave_type": leave_type,
						"total_days": leave_balance,
						"half_day": 0 if float(leave_balance).is_integer() else 1,
						"half_day_date": ""
						if float(leave_balance).is_integer()
						else (
							half_day_date
							if half_day_date
							and half_day_date
							<= np_to_date + relativedelta(days=np_no_of_holidays)
							else np_to_date + relativedelta(days=np_no_of_holidays)
						),
					}
				)

			# Part 2: unpaid (Nghỉ không lương)
			if float(leave_balance).is_integer():
				vals.append(
					{
						"from_date": np_to_date + relativedelta(days=np_no_of_holidays + 1),
						"to_date": to_date,
						"leave_type": leave_type_extra,
						"total_days": extra_number,
						"half_day": (
							half_day
							if (half_day_date and
								(np_to_date + relativedelta(days=nkl_no_of_holidays + 1)) <= half_day_date <= to_date)
							else 0
						),
						"half_day_date": (
							half_day_date
							if (half_day_date and
								(np_to_date + relativedelta(days=nkl_no_of_holidays + 1)) <= half_day_date <= to_date)
							else ""
						),
					}
				)
			else:
				# first unpaid is a half day to complete the day
				vals.append(
					{
						"from_date": np_to_date + relativedelta(days=np_no_of_holidays),
						"to_date": np_to_date + relativedelta(days=np_no_of_holidays),
						"leave_type": leave_type_extra,
						"total_days": 0.5,
						"half_day": 1,
						"half_day_date": np_to_date + relativedelta(days=np_no_of_holidays),
					}
				)
				if extra_number > 0.5:
					vals.append(
						{
							"from_date": np_to_date
							+ relativedelta(days=np_no_of_holidays + 1),
							"to_date": to_date,
							"leave_type": leave_type_extra,
							"total_days": extra_number - 0.5,
							"half_day": (
								half_day
								if (
									half_day_date
									and (np_to_date + relativedelta(days=np_no_of_holidays + 1))
									<= half_day_date
									<= to_date
								)
								else 0
							),
							"half_day_date": (
								half_day_date
								if (
									half_day_date
									and (np_to_date + relativedelta(days=np_no_of_holidays + 1))
									<= half_day_date
									<= to_date
								)
								else ""
							),
						}
					)

	return vals


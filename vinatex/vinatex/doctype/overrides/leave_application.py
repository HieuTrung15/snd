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
from frappe.utils import date_diff, flt, getdate
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

# from eupapp.eup_hr.doctype.xac_nhan_cham_cong.xac_nhan_cham_cong import update_event
# from eupapp.eupapp.doctype.overrides.workflow import gen_approve_channel


class VntLeaveApplication(LeaveApplication):
	LEAVE_TYPE = "Công tác"
	
	def save(self):
		super().save()
		# notify(self, self.employee_name, self.leave_approver)
			
			
	def before_submit(self):
		self.status = "Approved"


	def on_update(self):
		# chuyển sang theo dõi workflow_state
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)


	def validate(self):
		days_notice = 0
		if getattr(self, "leave_type", None) == 'Nghỉ phép năm' and getattr(self, "from_date", None) and getattr(self, "to_date", None):
			days_diff = date_diff(self.from_date, self.to_date) + 1
			# "Nghỉ 02 ngày phải gửi đơn trước 01 ngày.
			#  Nghỉ từ 03 - 06 ngày, phải gửi đơn trước ít nhất 03 ngày.
			#  Nghỉ từ 07 ngày trở lên, phải gửi đơn trước ít nhất 14 ngày."
			if days_diff == 2:
				days_notice = 1
			elif 3 <= days_diff <= 6:
				days_notice = 3
			elif days_diff >= 7:
				days_notice = 14
			if date_diff(self.from_date, frappe.utils.nowdate()) < days_notice:
				frappe.throw(_("Đơn nghỉ phép năm từ {0} ngày trở lên phải gửi trước ít nhất {1} ngày. Vui lòng kiểm tra lại.").format(days_diff, days_notice), indicator='orange')
		if getattr(self, "leave_type", None) == 'Nghỉ không hưởng lương' and getattr(self, "from_date", None) and getattr(self, "to_date", None):
			days_diff = date_diff(self.to_date, self.from_date) + 1
			# "Nghỉ dưới 7 ngày báo trước ít nhất 3 ngày.
			# Nghỉ trên 7 ngày báo trước ít nhất 14 ngày."
			if days_diff < 7:
				days_notice = 3
			else:
				days_notice = 14
			if date_diff(self.from_date, frappe.utils.nowdate()) < days_notice:
				frappe.throw(_("Đơn nghỉ không hưởng lương từ {0} ngày trở lên phải gửi trước ít nhất {1} ngày. Vui lòng kiểm tra lại.").format(days_diff, days_notice))
		if getattr(self, "leave_type", None) == 'Lao động nam nghỉ do có vợ sinh con' and getattr(self, "from_date", None) and getattr(self, "to_date", None):
			# "Nghỉ 02 ngày phải gửi đơn trước 01 ngày.
			# Nghỉ từ 03 - 06 ngày, phải gửi đơn trước ít nhất 03 ngày.
			# Nghỉ từ 07 ngày trở lên, phải gửi đơn trước ít nhất 14 ngày."
			days_diff = date_diff(self.from_date, self.to_date) + 1
			if days_diff == 2:
				days_notice = 1
			elif 3 <= days_diff <= 6:
				days_notice = 3 
			elif days_diff >= 7:
				days_notice = 14
			if date_diff(self.from_date, frappe.utils.nowdate()) < days_notice:
				frappe.throw(_("Đơn nghỉ lao động nam do có vợ sinh con từ {0} ngày trở lên phải gửi trước ít nhất {1} ngày. Vui lòng kiểm tra lại.").format(days_diff, days_notice), indicator='orange')


def _handle_state_transition(doc: Document):
	prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)
	pending_state = "Chờ lãnh đạo duyệt"
	approved_state = "Đã duyệt"
	if curr_state == pending_state and prev_state != pending_state:
		_notify_to_approver(doc)
	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		_notify_to_approver_2(doc)

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt' or \
		prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Đã duyệt':
		_check_state_to_close_todo(doc, doc.get("leave_approver"))

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Đã duyệt':
		_check_state_to_close_todo(doc, doc.get("custom_second_approver"))


def _notify_to_approver(doc: Document):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo duyệt'."""
	leave_type = doc.get("leave_type")
	approver_emp = doc.get("leave_approver")
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, [approver_emp])
	# tạo todo cho người duyệt
	ensure_todo(doc, approver_emp)
		

def _notify_to_approver_2(doc: Document):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo duyệt'."""
	leave_type = doc.get("leave_type")
	approver_emp = doc.get("custom_second_approver")
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký {0} của {1} đang chờ lãnh đạo duyệt.").format(leave_type or _("(không rõ)"), doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, [approver_emp])
	# tạo todo cho người duyệt
	ensure_todo(doc, approver_emp)


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
	description = _("Duyệt phiếu đăng ký {0} do {1} tạo. Nghỉ từ {2} đến {3}, tổng số ngày nghỉ: {4}").format(leave_type, employee, from_date, to_date, total_leave_days)
   
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


@frappe.whitelist()
def get_leave_approver(employee: str):
	# lấy approver trên Employee trước
	emp = frappe.db.get_value("Employee", employee, ["leave_approver", "department", "custom_designation_group"], as_dict=True)
	if not emp:
		return None
	approver = emp.leave_approver

	# nếu chưa có và có department → tìm trong Department Approver
	if not approver and emp.department and emp.custom_designation_group == 'Chuyên viên, Nhân viên':
		# ƯU TIÊN custom flag custom_level_1 = 1
		approver = frappe.db.get_value(
			"Department Approver",
			{
				"parent": emp.department,
				"parentfield": "leave_approvers",
				"custom_level_1": 1,
			},
			"approver",
		)

	else:
		approver = frappe.db.get_value(
			"Department Approver",
			{
				"parent": emp.department,
				"parentfield": "leave_approvers",
				"custom_level_2": 1,
			},
			"approver",
		)

	return approver


@frappe.whitelist()
def get_leave_approver_level_2(employee: str):
	# lấy approver trên Employee trước
	emp = frappe.db.get_value("Employee", employee, ["leave_approver", "department"], as_dict=True)
	if not emp:
		return None

	# nếu chưa có và có department → tìm trong Department Approver
		# ƯU TIÊN custom flag custom_level_2 = 1
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
	else :
		approver = emp.leave_approver

	return approver

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


def system_notification(message, doctype, docname, emails=''):
	subject = {
		"type": "Alert",
				"subject": message,
				'document_type': doctype,
				'document_name': docname
	}
	make_notification_logs(subject, emails)
	
	
def notify(self, actor, receiver):
	# url = get_url_to_form(self.doctype, self.name)
	message = _(f"Phiếu đăng ký nghỉ phép") + " của " + actor
	system_notification(message, self.doctype, self.name, receiver)



# def _handle_state_transition(doc: Document):
#     workflow = get_workflow_name(doc.doctype)
#     frappe.throw(F"{workflow}")
#     prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)
#     pending_state = "Chờ lãnh đạo duyệt"
#     approved_state = "Đã duyệt"

#     if curr_state == pending_state and prev_state != pending_state:
#         _notify_to_approver(doc)

#     total_leave_days = flt(doc.get("total_leave_days") or 0)
#     requires_second_level = total_leave_days > 3 and bool(doc.get("custom_second_approver"))

#     if not requires_second_level:
#         return

#     if prev_state == pending_state and curr_state == approved_state:
#         current_user = getattr(getattr(frappe, "session", None), "user", None)
#         second_approver = doc.get("custom_second_approver")
#         if current_user and second_approver and frappe.utils.cstr(current_user) == frappe.utils.cstr(second_approver):
#             return
#         _reroute_to_second_approver(doc, pending_state)


# def _reroute_to_second_approver(doc: Document, target_state: str):
#     """Đưa phiếu trở lại trạng thái chờ duyệt và thông báo cho cấp duyệt thứ hai."""
#     if not doc.name:
#         return
#     try:
#         frappe.db.set_value(doc.doctype, doc.name, "workflow_state", target_state, update_modified=False)
#     except Exception:
#         pass
#     doc.workflow_state = target_state
#     _notify_to_approver_2(doc)

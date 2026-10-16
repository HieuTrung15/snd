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
from frappe.utils import add_days, cint, date_diff, flt, getdate, get_link_to_form, formatdate, nowdate

from frappe.model.document import Document

from dateutil.relativedelta import relativedelta
from erpnext.buying.doctype.supplier_scorecard.supplier_scorecard import daterange
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from hrms.hr.doctype.leave_application.leave_application import (
	LeaveApplication,
	get_allocation_expiry_for_cf_leaves,
	get_leave_allocation_records,
	get_leave_entries,
	get_manually_expired_leaves,
	get_number_of_leave_days as hrms_get_number_of_leave_days,
	is_lwp,
)
from hrms.hr.doctype.leave_ledger_entry.leave_ledger_entry import (
	create_leave_ledger_entry,
	delete_ledger_entry,
)
from hrms.hr.utils import get_holiday_dates_for_employee
from frappe.utils.data import get_url_to_form
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.model.workflow import get_workflow_name
from vinatex.patches.utils.rocket_chat import send_rocket_message
from vinatex.vinatex.doctype.utils.todo_notification_sync import close_todos_and_mark_notifications
from vinatex.vnt_hr.attendance_processing import (
	build_shift_windows,
	classify_work_date,
	get_active_employees,
	load_holiday_context,
	process_attendance,
)
from vinatex.vnt_hr.shift_management.constants import MAX_MANUAL_GENERATION_DAYS

# from eupapp.eup_hr.doctype.xac_nhan_cham_cong.xac_nhan_cham_cong import update_event
# from eupapp.eupapp.doctype.overrides.workflow import gen_approve_channel


class AttendanceAlreadyMarkedError(frappe.ValidationError):
	pass


class VntLeaveApplication(LeaveApplication):
	LEAVE_TYPE = "Công tác"
	AUTO_APPROVED_WORKFLOW_STATE = "Đã duyệt"
	HR_ROLES = {"HR User", "HR Manager", "System Manager"}

	def insert(
		self,
		ignore_permissions=None,
		ignore_links=None,
		ignore_if_duplicate=False,
		ignore_mandatory=None,
		set_name=None,
		set_child_names=True,
	):
		"""Create every new leave request as an approved, submitted document.

		Employees still need Create permission and may only apply for their own
		Employee record.  The internal permission bypass is deliberately limited to
		the Submit step, which standard Employees do not have permission to perform.
		"""
		caller_ignores_permissions = bool(ignore_permissions)
		if not caller_ignores_permissions:
			# Never trust an ``ignore_permissions`` flag received in document JSON.
			previous_ignore_permissions = self.flags.ignore_permissions
			self.flags.ignore_permissions = False
			try:
				self.check_permission("create")
				self._validate_employee_scope()
			finally:
				self.flags.ignore_permissions = previous_ignore_permissions

		self._set_auto_approved_values()
		self.docstatus = 1
		self.flags.vnt_auto_approved = True
		return super().insert(
			ignore_permissions=True,
			ignore_links=ignore_links,
			ignore_if_duplicate=ignore_if_duplicate,
			ignore_mandatory=ignore_mandatory,
			set_name=set_name,
			set_child_names=set_child_names,
		)

	def _validate_employee_scope(self):
		if frappe.session.user == "Administrator" or self.HR_ROLES.intersection(frappe.get_roles()):
			return

		employee_user = frappe.db.get_value("Employee", self.employee, "user_id")
		if not employee_user or employee_user != frappe.session.user:
			frappe.throw(
				_("Bạn chỉ có thể tạo phiếu nghỉ cho hồ sơ nhân viên của chính mình."),
				frappe.PermissionError,
			)

	def _set_auto_approved_values(self):
		self.status = "Approved"
		if self.meta.has_field("workflow_state"):
			self.workflow_state = self.AUTO_APPROVED_WORKFLOW_STATE

		# These legacy fields belonged to the removed approval flow. Clearing them
		# prevents old client values from creating approval notifications or ToDos.
		for fieldname in (
			"leave_approver",
			"leave_approver_name",
			"custom_approver",
			"custom_approver_name",
			"custom_second_approver",
			"custom_second_approver_name",
			"custom_reject_reason",
		):
			if self.meta.has_field(fieldname):
				self.set(fieldname, None)

	def before_submit(self):
		self._set_auto_approved_values()

	def after_insert(self):
		# No approval request is sent because the document is already approved.
		pass

	def before_cancel(self):
		super().before_cancel()
		if self.meta.has_field("workflow_state"):
			self.workflow_state = "Đã hủy"

	def on_cancel(self):
		super().on_cancel()
		_check_emp_checkin_after_cancel(self)


	def on_update(self):
		if self.flags.get("vnt_auto_approved"):
			return
		# chuyển sang theo dõi workflow_state
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)

	def validate_for_self_approval(self):
		# Self approval is the explicit business rule for this installation.
		return

	def validate_balance_leaves(self):
		"""Use the same resolved ca/kíp calendar as attendance reports."""
		shift_days = _get_shift_aware_leave_days(
			self.employee,
			self.leave_type,
			self.from_date,
			self.to_date,
			self.half_day,
			self.half_day_date,
		)
		if shift_days is None:
			return super().validate_balance_leaves()

		self.flags.vnt_leave_windows = shift_days.windows
		precision = cint(frappe.db.get_single_value("System Settings", "float_precision")) or 2
		self.total_leave_days = shift_days.total_days
		if self.total_leave_days <= 0:
			frappe.throw(
				_("Các ngày đã chọn đều là ngày nghỉ hoặc ngày không được xếp ca; không cần tạo phiếu nghỉ."),
			)

		if not is_lwp(self.leave_type):
			leave_balance = get_leave_balance_on(
				self.employee,
				self.leave_type,
				self.from_date,
				self.to_date,
				consider_all_leaves_in_the_allocation_period=True,
				for_consumption=True,
			)
			leave_balance_for_consumption = flt(
				leave_balance.get("leave_balance_for_consumption"), precision
			)
			if leave_balance_for_consumption < self.total_leave_days or not leave_balance_for_consumption:
				self.show_insufficient_balance_message(leave_balance_for_consumption)

	def update_attendance(self):
		if self.status != "Approved":
			return

		shift_days = _get_shift_aware_leave_days(
			self.employee,
			self.leave_type,
			self.from_date,
			self.to_date,
			self.half_day,
			self.half_day_date,
		)
		if shift_days is None:
			return super().update_attendance()

		self.flags.vnt_leave_windows = shift_days.windows
		for attendance_date in _date_range(self.from_date, self.to_date):
			date_string = attendance_date.strftime("%Y-%m-%d")
			attendance_name = frappe.db.exists(
				"Attendance",
				{
					"employee": self.employee,
					"attendance_date": date_string,
					"docstatus": ("!=", 2),
				},
			)
			if attendance_date not in shift_days.counted_dates:
				if attendance_name:
					attendance = frappe.get_doc("Attendance", attendance_name)
					attendance.flags.ignore_permissions = True
					if attendance.docstatus == 1:
						attendance.cancel()
					frappe.delete_doc("Attendance", attendance_name, force=1)
				continue

			self.create_or_update_attendance(attendance_name, date_string)

	def create_or_update_attendance(self, attendance_name, date):
		super().create_or_update_attendance(attendance_name, date)
		window = (self.flags.get("vnt_leave_windows") or {}).get(getdate(date))
		if not window:
			window = _get_shift_window(self.employee, date)
		if not window or not window.get("shift_type"):
			return

		attendance_name = attendance_name or frappe.db.get_value(
			"Attendance",
			{
				"employee": self.employee,
				"attendance_date": getdate(date),
				"leave_application": self.name,
				"docstatus": ("<", 2),
			},
			"name",
		)
		if attendance_name and not frappe.db.get_value("Attendance", attendance_name, "shift"):
			frappe.db.set_value(
				"Attendance", attendance_name, "shift", window.shift_type, update_modified=False
			)

	def _get_ledger_holiday_list(self, raise_exception=True):
		# Kíp/ca kế hoạch is the authoritative calendar. A conventional Employee
		# Holiday List is optional and may not exist for factory workers.
		if _get_shift_context(self.employee, self.from_date, self.to_date):
			return get_holiday_list_for_employee(self.employee, raise_exception=False) or ""
		return get_holiday_list_for_employee(
			self.employee, raise_exception=raise_exception
		) or ""

	def create_leave_ledger_entry(self, submit=True):
		"""Create the ledger without requiring a duplicate office holiday calendar."""
		if self.status != "Approved" and submit:
			return

		expiry_date = get_allocation_expiry_for_cf_leaves(
			self.employee, self.leave_type, self.to_date, self.from_date
		)
		lwp = frappe.db.get_value("Leave Type", self.leave_type, "is_lwp")
		if expiry_date:
			self.create_ledger_entry_for_intermediate_allocation_expiry(expiry_date, submit, lwp)
			return

		alloc_on_from_date, alloc_on_to_date = self.get_allocation_based_on_application_dates()
		if self.is_separate_ledger_entry_required(alloc_on_from_date, alloc_on_to_date):
			self.create_separate_ledger_entries(alloc_on_from_date, alloc_on_to_date, submit, lwp)
			return

		raise_exception = False if frappe.flags.in_patch else True
		args = {
			"leaves": self.total_leave_days * -1,
			"from_date": self.from_date,
			"to_date": self.to_date,
			"is_lwp": lwp,
			"holiday_list": self._get_ledger_holiday_list(raise_exception),
		}
		create_leave_ledger_entry(self, args, submit)

	def create_separate_ledger_entries(self, alloc_on_from_date, alloc_on_to_date, submit, lwp):
		"""Split ledger entries with the same shift-aware day calculation."""
		if (
			submit
			and alloc_on_from_date
			and alloc_on_to_date
			and add_days(alloc_on_from_date.to_date, 1) != alloc_on_to_date.from_date
		):
			frappe.throw(
				_(
					"Leave Application period cannot be across two non-consecutive leave allocations {0} and {1}."
				).format(
					get_link_to_form("Leave Allocation", alloc_on_from_date.name),
					get_link_to_form("Leave Allocation", alloc_on_to_date),
				)
			)

		raise_exception = False if frappe.flags.in_patch else True
		if alloc_on_from_date:
			first_alloc_end = alloc_on_from_date.to_date
			second_alloc_start = add_days(alloc_on_from_date.to_date, 1)
		else:
			first_alloc_end = add_days(alloc_on_to_date.from_date, -1)
			second_alloc_start = alloc_on_to_date.from_date

		leaves_in_first_alloc = get_number_of_leave_days(
			self.employee,
			self.leave_type,
			self.from_date,
			first_alloc_end,
			self.half_day,
			self.half_day_date,
		)
		leaves_in_second_alloc = get_number_of_leave_days(
			self.employee,
			self.leave_type,
			second_alloc_start,
			self.to_date,
			self.half_day,
			self.half_day_date,
		)
		args = {
			"is_lwp": lwp,
			"holiday_list": self._get_ledger_holiday_list(raise_exception),
		}
		if leaves_in_first_alloc:
			args.update(
				from_date=self.from_date,
				to_date=first_alloc_end,
				leaves=leaves_in_first_alloc * -1,
			)
			create_leave_ledger_entry(self, args, submit)
		if leaves_in_second_alloc:
			args.update(
				from_date=second_alloc_start,
				to_date=self.to_date,
				leaves=leaves_in_second_alloc * -1,
			)
			create_leave_ledger_entry(self, args, submit)

	def create_ledger_entry_for_intermediate_allocation_expiry(self, expiry_date, submit, lwp):
		"""Split an expiring allocation without reverting to the office calendar."""
		raise_exception = False if frappe.flags.in_patch else True
		leaves = get_number_of_leave_days(
			self.employee,
			self.leave_type,
			self.from_date,
			expiry_date,
			self.half_day,
			self.half_day_date,
		)
		args = {
			"is_lwp": lwp,
			"holiday_list": self._get_ledger_holiday_list(raise_exception),
		}
		if leaves:
			args.update(
				from_date=self.from_date,
				to_date=expiry_date,
				leaves=leaves * -1,
			)
			create_leave_ledger_entry(self, args, submit)

		if getdate(expiry_date) != getdate(self.to_date):
			start_date = add_days(expiry_date, 1)
			leaves = get_number_of_leave_days(
				self.employee,
				self.leave_type,
				start_date,
				self.to_date,
				self.half_day,
				self.half_day_date,
			)
			if leaves:
				args.update(from_date=start_date, to_date=self.to_date, leaves=leaves * -1)
				create_leave_ledger_entry(self, args, submit)


	def validate_attendance(self):
		attendance_dates = frappe.get_all(
			"Attendance",
			filters={
				"employee": self.employee,
				"attendance_date": ("between", [self.from_date, self.to_date]),
				"status": ("in", ["Present", "Work From Home"]),
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


def _date_range(from_date, to_date):
	current_date = getdate(from_date)
	to_date = getdate(to_date)
	while current_date <= to_date:
		yield current_date
		current_date = add_days(current_date, 1)


def _get_shift_context(employee, from_date, to_date):
	"""Resolve the employee calendar using the shared attendance engine."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	cache = getattr(frappe.local, "vnt_leave_shift_context", None)
	if cache is None:
		cache = frappe.local.vnt_leave_shift_context = {}
	cache_key = (employee, from_date, to_date)
	if cache_key in cache:
		return cache[cache_key]

	employees = get_active_employees(from_date, to_date, [employee])
	if not employees:
		cache[cache_key] = None
		return None

	employee_row = employees[0]
	all_windows = build_shift_windows(employees, from_date, to_date)
	windows = {
		work_date: all_windows.get((employee, work_date))
		for work_date in _date_range(from_date, to_date)
	}
	uses_shift_calendar = bool(
		employee_row.get("default_shift")
		or employee_row.get("custom_shift_group")
		or any(
			window
			and (window.get("shift_type") or window.get("shift_group") or window.get("assignment_source"))
			for window in windows.values()
		)
	)
	if not uses_shift_calendar:
		cache[cache_key] = None
		return None

	for work_date, window in windows.items():
		if window and window.get("plan_action") == "ERROR":
			frappe.throw(
				_("Không thể xác định ca kế hoạch ngày {0}: {1}").format(
					formatdate(work_date), window.get("plan_error") or _("cấu hình ca/kíp không hợp lệ")
				)
			)

	holiday_context = load_holiday_context(employees, all_windows, from_date, to_date)
	context = frappe._dict(
		employee=employee_row,
		windows=windows,
		holiday_context=holiday_context,
	)
	cache[cache_key] = context
	return context


def _get_shift_window(employee, work_date):
	context = _get_shift_context(employee, work_date, work_date)
	return context and context.windows.get(getdate(work_date))


def _get_shift_aware_leave_days(
	employee,
	leave_type,
	from_date,
	to_date,
	half_day=None,
	half_day_date=None,
):
	if not (employee and leave_type and from_date and to_date):
		return None

	context = _get_shift_context(employee, from_date, to_date)
	if not context:
		return None

	include_holiday = cint(frappe.db.get_value("Leave Type", leave_type, "include_holiday"))
	counted_dates = set()
	for work_date in _date_range(from_date, to_date):
		if include_holiday:
			counted_dates.add(work_date)
			continue
		window = context.windows.get(work_date)
		if classify_work_date(context.employee, window, context.holiday_context) == "work":
			counted_dates.add(work_date)

	total_days = flt(len(counted_dates))
	half_day_date = getdate(half_day_date) if half_day_date else None
	if cint(half_day):
		if not half_day_date and getdate(from_date) == getdate(to_date):
			half_day_date = getdate(from_date)
		if half_day_date in counted_dates:
			total_days -= 0.5

	return frappe._dict(
		total_days=total_days,
		counted_dates=counted_dates,
		windows=context.windows,
	)


@frappe.whitelist()
def get_number_of_leave_days(
	employee,
	leave_type,
	from_date,
	to_date,
	half_day=None,
	half_day_date=None,
	holiday_list=None,
):
	"""Return leave days from ca/kíp; fall back to the standard HRMS calendar."""
	shift_days = _get_shift_aware_leave_days(
		employee, leave_type, from_date, to_date, half_day, half_day_date
	)
	if shift_days is not None:
		return shift_days.total_days
	return hrms_get_number_of_leave_days(
		employee,
		leave_type,
		from_date,
		to_date,
		half_day,
		half_day_date,
		holiday_list,
	)


def _get_leaves_for_period(employee, leave_type, from_date, to_date, skip_expired_leaves=True):
	"""Read leave consumption using the same calendar that created the ledger."""
	leave_entries = get_leave_entries(employee, leave_type, from_date, to_date)
	leave_days = 0.0
	for leave_entry in leave_entries:
		inclusive_period = (
			leave_entry.from_date >= getdate(from_date)
			and leave_entry.to_date <= getdate(to_date)
		)
		if inclusive_period and leave_entry.transaction_type == "Leave Encashment":
			leave_days += leave_entry.leaves
		elif (
			inclusive_period
			and leave_entry.transaction_type == "Leave Allocation"
			and leave_entry.is_expired
			and not skip_expired_leaves
		):
			leave_days += leave_entry.leaves
		elif leave_entry.transaction_type == "Leave Application":
			# The persisted quantity is authoritative when the whole application is
			# inside the requested period. Recalculate only the intersecting part.
			if inclusive_period:
				leave_days += leave_entry.leaves
				continue

			entry_from = max(getdate(leave_entry.from_date), getdate(from_date))
			entry_to = min(getdate(leave_entry.to_date), getdate(to_date))
			half_day = 0
			half_day_date = None
			if leave_entry.leaves % 1:
				half_day = 1
				half_day_date = frappe.db.get_value(
					"Leave Application", leave_entry.transaction_name, "half_day_date"
				)
			leave_days -= get_number_of_leave_days(
				employee,
				leave_type,
				entry_from,
				entry_to,
				half_day,
				half_day_date,
				holiday_list=leave_entry.holiday_list,
			)
	return leave_days


def _get_new_and_cf_leaves_taken(allocation, cf_expiry):
	cf_leaves_taken = _get_leaves_for_period(
		allocation.employee, allocation.leave_type, allocation.from_date, cf_expiry
	)
	new_leaves_taken = _get_leaves_for_period(
		allocation.employee,
		allocation.leave_type,
		add_days(cf_expiry, 1),
		allocation.to_date,
	)
	if abs(cf_leaves_taken) > allocation.unused_leaves:
		new_leaves_taken += -(abs(cf_leaves_taken) - allocation.unused_leaves)
		cf_leaves_taken = -allocation.unused_leaves
	return new_leaves_taken, cf_leaves_taken


def _get_remaining_leaves(
	employee,
	leave_type,
	allocation,
	leaves_taken,
	date,
	cf_expiry,
	manually_expired_leaves,
):
	def limit_to_remaining_period(remaining_leaves, end_date):
		if remaining_leaves > 0:
			remaining_days = get_number_of_leave_days(employee, leave_type, date, end_date)
			remaining_leaves = min(remaining_days, remaining_leaves)
		return remaining_leaves

	if cf_expiry and allocation.unused_leaves:
		new_leaves_taken, cf_leaves_taken = _get_new_and_cf_leaves_taken(allocation, cf_expiry)
		if getdate(date) > getdate(cf_expiry):
			cf_leaves = remaining_cf_leaves = 0
		else:
			cf_leaves = flt(allocation.unused_leaves) + flt(cf_leaves_taken)
			remaining_cf_leaves = limit_to_remaining_period(cf_leaves, cf_expiry)
		leave_balance = (
			flt(allocation.new_leaves_allocated)
			+ flt(new_leaves_taken)
			+ flt(cf_leaves)
			+ flt(manually_expired_leaves)
		)
		leave_balance_for_consumption = (
			flt(allocation.new_leaves_allocated)
			+ flt(new_leaves_taken)
			+ flt(remaining_cf_leaves)
			+ flt(manually_expired_leaves)
		)
	else:
		leave_balance = leave_balance_for_consumption = (
			flt(allocation.total_leaves_allocated)
			+ flt(leaves_taken)
			+ flt(manually_expired_leaves)
		)

	return frappe._dict(
		leave_balance=leave_balance,
		leave_balance_for_consumption=limit_to_remaining_period(
			leave_balance_for_consumption, allocation.to_date
		),
	)


@frappe.whitelist()
def get_leave_balance_on(
	employee,
	leave_type,
	date,
	to_date=None,
	consider_all_leaves_in_the_allocation_period=False,
	for_consumption=False,
):
	"""Return a leave balance consistent with shift-aware ledger quantities."""
	to_date = to_date or nowdate()
	allocation_records = get_leave_allocation_records(employee, date, leave_type)
	allocation = allocation_records.get(leave_type, frappe._dict())
	if not allocation:
		return frappe._dict(leave_balance=0, leave_balance_for_consumption=0) if cint(
			for_consumption
		) else 0

	end_date = allocation.to_date if cint(consider_all_leaves_in_the_allocation_period) else date
	cf_expiry = get_allocation_expiry_for_cf_leaves(
		employee, leave_type, to_date, allocation.from_date
	)
	leaves_taken = _get_leaves_for_period(employee, leave_type, allocation.from_date, end_date)
	manually_expired_leaves = get_manually_expired_leaves(
		employee, leave_type, allocation.from_date, end_date
	)
	remaining_leaves = _get_remaining_leaves(
		employee,
		leave_type,
		allocation,
		leaves_taken,
		date,
		cf_expiry,
		manually_expired_leaves,
	)
	return remaining_leaves if cint(for_consumption) else remaining_leaves.leave_balance


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
	"""Recalculate past work from checkins after HR cancels a leave request."""
	cancelled_attendance_names = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"leave_application": doc.name,
			"attendance_date": ("between", [doc.from_date, doc.to_date]),
			"docstatus": 2,
		},
		pluck="name",
	)
	if cancelled_attendance_names:
		checkin_names = frappe.get_all(
			"Employee Checkin",
			filters={"attendance": ("in", cancelled_attendance_names)},
			pluck="name",
		)
		for checkin_name in checkin_names:
			frappe.db.set_value(
				"Employee Checkin", checkin_name, "attendance", None, update_modified=False
			)

	chunk_start = getdate(doc.from_date)
	to_date = getdate(doc.to_date)
	while chunk_start <= to_date:
		chunk_end = min(add_days(chunk_start, MAX_MANUAL_GENERATION_DAYS - 1), to_date)
		process_attendance(
			chunk_start,
			chunk_end,
			employee_names=[doc.employee],
		)
		chunk_start = add_days(chunk_end, 1)


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
	close_todos_and_mark_notifications(names)


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
	# Leave Application is auto-approved; the standard client may still call this
	# endpoint, but no approver should be assigned or notified.
	return None


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
	effective_date = to_dt

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
		if effective_date > expiry_date:
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

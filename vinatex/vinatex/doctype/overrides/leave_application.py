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

# from eupapp.eup_hr.doctype.xac_nhan_cham_cong.xac_nhan_cham_cong import update_event
# from eupapp.eupapp.doctype.overrides.workflow import gen_approve_channel


class VntLeaveApplication(LeaveApplication):
    pass


#     def on_update_after_submit(self):
#         if self.workflow_state in ["Approved", "Rejected", "Cancelled"]:
#             if self.workflow_state == "Approved":
#                 self.create_timesheet()
#                 active_ap = frappe.db.get_all(
#                     "Approve Channels",
#                     filters={"origin": self.name, "overall_status": "Open"},
#                     fields=["name"],
#                 )
#                 for ap in active_ap:
#                     frappe.db.set_value(
#                         "Approve Channels", ap["name"], "overall_status", "Closed"
#                     )
#             self.update_attendance()
#             self.update_xncc()

#     def clean_approve_channels(self):
#         roles = frappe.get_roles(frappe.session.user)

#         if self.workflow_state != "Approved" or "HR Manager" in roles:
#             approve_channel = frappe.get_all(
#                 "Approve Channels",
#                 filters={"origin": self.name, "overall_status": "Open"},
#                 fields=["name"],
#             )
#             if approve_channel:
#                 doc = frappe.get_doc("Approve Channels", approve_channel[0]["name"])
#                 doc.flags.ignore_permissions = 1
#                 doc.overall_status = "Cancelled"
#                 doc.save()

#         elif self.workflow_state == "Approved" and "HR Manager" not in roles:
#             frappe.throw(_("Do not have right to cancel approved Document!"))

#     def on_update(self):
#         self.validate_total_time()

#         employee_location = frappe.db.get_value(
#             "Employee", {"employee": self.employee}, "default_work_location"
#         )
#         permission = frappe.db.get_value(
#             "EuP Settings",
#             {
#                 "setting_name": "saturday_half_day_permission",
#                 "location": employee_location,
#             },
#             "value",
#         )

#         if not permission or str(permission) == "0":
#             if self.half_day and getdate(self.half_day_date).weekday() == 5:
#                 frappe.throw(_("Không thể tạo nghỉ nửa ngày vào thứ Bảy"))

#         if self.workflow_state in ["Approved", "Rejected"]:
#             self.update_attendance()

#         holidays = get_holiday_dates_for_employee(
#             self.employee, self.from_date, self.to_date
#         )
#         if self.half_day_date and getdate(self.half_day_date) in set(
#             getdate(x) for x in holidays
#         ):
#             frappe.throw(_("Can not set half day date on holiday"))

#     def on_submit(self):
#         if self.workflow_state in ["Approved", "Rejected"]:
#             self.update_attendance()
#         self.validate_back_dated_application()

#         # notify leave applier about approval
#         if frappe.db.get_single_value("HR Settings", "send_leave_notification"):
#             self.notify_employee()

#         self.create_leave_ledger_entry()
#         self.reload()

#         timesheets = frappe.db.get_all(
#             "Timesheet",
#             fields=["name"],
#             filters={
#                 "employee": self.employee,
#                 "docstatus": 0,
#                 "leave_application": self.name,
#             },
#         )
#         for ts in timesheets:
#             doc = frappe.get_doc("Timesheet", ts["name"])
#             doc.submit()

#         self.create_timesheet()
#         gen_approve_channel(self, self.custom_print_format)

#     def validate_total_time(self):
#         employee_shift = frappe.get_all(
#             "Employee", filters={"name": self.employee}, fields=["default_shift"]
#         )
#         total_time = 8
#         if employee_shift and employee_shift[0].get("default_shift"):
#             st = frappe.get_all(
#                 "Shift Type",
#                 filters={"name": employee_shift[0]["default_shift"]},
#                 fields=["total_time"],
#                 limit=1,
#             )
#             if st:
#                 total_time = int(st[0].get("total_time") or 8)

#         child_hours = sum(
#             frappe.get_all(
#                 "Leave Application Item", filters={"parent": self.name}, pluck="hours"
#             )
#             or [0]
#         )
#         if child_hours > total_time:
#             frappe.throw(_(f"Thời gian làm việc không thể lớn hơn {total_time}h"))

#     def validate_balance_leaves(self):
#         if self.from_date and self.to_date:
#             self.total_leave_days = get_number_of_leave_days(
#                 self.employee,
#                 self.leave_type,
#                 self.from_date,
#                 self.to_date,
#                 self.half_day,
#                 self.half_day_date,
#             )

#         if (self.total_leave_days or 0) <= 0:
#             frappe.throw(
#                 _(
#                     "The day(s) on which you are applying for leave are holidays. "
#                     "You need not apply for leave."
#                 )
#             )

#         if not is_lwp(self.leave_type):
#             leave_balance = get_leave_balance_on(
#                 self.employee,
#                 self.leave_type,
#                 self.from_date,
#                 self.to_date,
#                 consider_all_leaves_in_the_allocation_period=True,
#                 for_consumption=True,
#             )
#             self.leave_balance = leave_balance.get("leave_balance") or 0
#             self.extra_number = max(self.total_leave_days - self.leave_balance, 0)
#             leave_balance_for_consumption = leave_balance.get(
#                 "leave_balance_for_consumption"
#             )

#             if (
#                 self.status != "Rejected"
#                 and (not leave_balance_for_consumption or
#                      leave_balance_for_consumption < self.total_leave_days)
#             ):
#                 if self.leave_type != "Nghỉ phép năm":
#                     self.show_insufficient_balance_message(
#                         leave_balance_for_consumption
#                     )

#     def update_attendance(self):
#         if self.status != "Approved":
#             return

#         if (
#             self.leave_type != "Nghỉ phép năm"
#             or not self.extra_number
#             or not self.leave_type_details
#         ):
#             super(EupLeaveApplication, self).update_attendance()
#             return

#         # split by leave_type_details
#         for item in self.leave_type_details:
#             holiday_dates = []
#             if not frappe.db.get_value("Leave Type", self.leave_type, "include_holiday"):
#                 holiday_dates = get_holiday_dates_for_employee(
#                     self.employee, item.from_date, item.to_date
#                 )

#             for dt in daterange(getdate(item.from_date), getdate(item.to_date)):
#                 date_str = dt.strftime("%Y-%m-%d")
#                 attendance_name = frappe.db.exists(
#                     "Attendance",
#                     {"employee": self.employee, "attendance_date": date_str, "docstatus": ["!=", 2]},
#                 )

#                 # Skip holidays; remove existing attendance on holidays
#                 if dt in holiday_dates:
#                     if attendance_name:
#                         attendance = frappe.get_doc("Attendance", attendance_name)
#                         attendance.flags.ignore_permissions = True
#                         if attendance.docstatus == 1:
#                             attendance.cancel()
#                         frappe.delete_doc("Attendance", attendance_name, force=1)
#                     continue

#                 self.create_or_update_attendance(attendance_name, date_str, item)

#     def update_xncc(self):
#         xncc = frappe.db.get_all(
#             "Xac nhan cham cong",
#             filters={
#                 "f_date": ["<=", self.to_date],
#                 "t_date": [">=", self.from_date],
#                 "docstatus": 0,
#                 "employee": self.employee,
#             },
#             fields=["name"],
#         )
#         for xn in xncc:
#             update_event(xn["name"])

#     def create_or_update_attendance(self, attendance_name, date, item=None):
#         if (
#             self.leave_type != "Nghỉ phép năm"
#             or not self.extra_number
#             or not self.leave_type_details
#         ):
#             super(EupLeaveApplication, self).create_or_update_attendance(
#                 attendance_name, date
#             )
#             return

#         status = (
#             "Half Day"
#             if item.half_day_date and getdate(date) == getdate(item.half_day_date)
#             else "On Leave"
#         )

#         if attendance_name:
#             frappe.db.set_value(
#                 "Attendance",
#                 attendance_name,
#                 {
#                     "status": status,
#                     "leave_type": item.leave_type,
#                     "leave_application": self.name,
#                 },
#             )
#         else:
#             doc = frappe.new_doc("Attendance")
#             doc.employee = self.employee
#             doc.employee_name = self.employee_name
#             doc.attendance_date = date
#             doc.company = self.company
#             doc.leave_type = item.leave_type
#             doc.leave_application = self.name
#             doc.status = status
#             doc.flags.ignore_validate = True
#             doc.insert(ignore_permissions=True)
#             doc.submit()

#     def create_leave_ledger_entry(self, submit=True):
#         if (
#             self.leave_type != "Nghỉ phép năm"
#             or not self.extra_number
#             or not self.leave_type_details
#         ):
#             super(EupLeaveApplication, self).create_leave_ledger_entry(submit)
#             return

#         if self.status != "Approved" and submit:
#             return

#         for item in self.leave_type_details:
#             expiry_date = get_allocation_expiry_for_cf_leaves(
#                 self.employee, item.leave_type, item.to_date, item.from_date
#             )
#             lwp = frappe.db.get_value("Leave Type", item.leave_type, "is_lwp") or 0

#             if expiry_date:
#                 self.create_ledger_entry_for_intermediate_allocation_expiry(
#                     expiry_date, submit, lwp
#                 )
#                 continue

#             alloc_on_from_date, alloc_on_to_date = self.get_allocation_based_on_application_dates(
#                 item.from_date, item.to_date, item.leave_type
#             )

#             if self.is_separate_ledger_entry_required(
#                 alloc_on_from_date, alloc_on_to_date
#             ):
#                 self.create_separate_ledger_entries(
#                     alloc_on_from_date, alloc_on_to_date, submit, lwp
#                 )
#                 continue

#             raise_exception = False if frappe.flags.in_patch else True
#             args = dict(
#                 leaves=item.total_days * -1,
#                 leave_type=item.leave_type,
#                 from_date=item.from_date,
#                 to_date=item.to_date,
#                 is_lwp=lwp,
#                 holiday_list=get_holiday_list_for_employee(
#                     self.employee, raise_exception=raise_exception
#                 )
#                 or "",
#             )
#             create_leave_ledger_entry(self, args, submit)

#     def get_allocation_based_on_application_dates(
#         self, from_date=None, to_date=None, leave_type=None
#     ) -> Tuple[Dict, Dict]:
#         """Returns allocation record for both from_date and to_date."""
#         if not from_date:
#             from_date = self.from_date
#         if not to_date:
#             to_date = self.to_date
#         if not leave_type:
#             leave_type = self.leave_type

#         if (
#             self.leave_type != "Nghỉ phép năm"
#             or not self.extra_number
#             or not self.leave_type_details
#         ):
#             return super(EupLeaveApplication, self).get_allocation_based_on_application_dates()

#         LeaveAllocation = DocType("Leave Allocation")

#         def _get_leave_allocation_record(date_):
#             allocation = (
#                 frappe.qb.from_(LeaveAllocation)
#                 .select(
#                     LeaveAllocation.name,
#                     LeaveAllocation.from_date,
#                     LeaveAllocation.to_date,
#                 )
#                 .where(
#                     (LeaveAllocation.employee == self.employee)
#                     & (LeaveAllocation.leave_type == leave_type)
#                     & (LeaveAllocation.docstatus == 1)
#                     & ((date_ >= LeaveAllocation.from_date) & (date_ <= LeaveAllocation.to_date))
#                 )
#             ).run(as_dict=True)
#             return allocation[0] if allocation else None

#         allocation_based_on_from_date = _get_leave_allocation_record(getdate(from_date))
#         allocation_based_on_to_date = _get_leave_allocation_record(getdate(to_date))
#         return allocation_based_on_from_date, allocation_based_on_to_date

#     # Document method to support custom cancel from client
#     @frappe.whitelist()
#     def cancel(self):
#         self.create_leave_ledger_entry(submit=False)
#         if frappe.db.get_single_value("HR Settings", "send_leave_notification"):
#             self.notify_employee()

#         self.cancel_timesheet()
#         self.cancel_attendance()
#         self.clean_approve_channels()

#         self.workflow_state = "Cancelled"
#         self.docstatus = 2
#         self.save()
#         self.reload()
#         self.update_xncc()
#         frappe.msgprint(_("Cancelled successfully!"))

#     def cancel_attendance(self):
#         attendance = frappe.db.sql(
#             """
#             SELECT name FROM `tabAttendance`
#             WHERE employee = %s
#               AND (attendance_date BETWEEN %s AND %s)
#               AND docstatus < 2
#               AND status IN ('On Leave', 'Half Day')
#             """,
#             (self.employee, self.from_date, self.to_date),
#             as_dict=True,
#         )
#         for row in attendance:
#             frappe.db.set_value("Attendance", row["name"], "docstatus", 2)

#     def cancel_timesheet(self):
#         frappe.db.set_value(
#             "Timesheet", {"leave_application": self.name}, "docstatus", 2
#         )

#     def create_timesheet(self):
#         # Parse start work time from self.from_time (HH:MM:SS)
#         h, m, s = map(int, str(self.from_time).split(":"))
#         start_work_time = timedelta(hours=h, minutes=m, seconds=s)

#         from_date = getdate(self.from_date)
#         to_date = getdate(self.to_date)

#         holidays = get_holiday_dates_for_employee(self.employee, from_date, to_date)

#         # Date list
#         date_list = []
#         cur_date = from_date
#         while cur_date <= to_date:
#             date_list.append(cur_date)
#             cur_date += timedelta(days=1)

#         tsheet_value = {
#             "doctype": "Timesheet",
#             "company": self.company,
#             "department": self.department,
#             "employee": self.employee,
#             "employee_name": self.employee_name,
#             "time_logs": [],
#             "status": "Submitted",
#             "leave_application": self.name,
#             "from_date": self.from_date,
#             "to_date": self.to_date,
#             "docstatus": 1,
#         }

#         for d in date_list:
#             if d in holidays:
#                 continue

#             shift_hours_offset = 0
#             for item in (self.task or []):
#                 if self.validate_timesheet(item.task, d):
#                     continue

#                 from_dt = datetime(d.year, d.month, d.day) + start_work_time + timedelta(
#                     hours=shift_hours_offset
#                 )
#                 to_dt = from_dt + timedelta(hours=(item.hours or 0))

#                 tsheet_value["time_logs"].append(
#                     {
#                         "activity_type": item.activity_type or "",
#                         "task": item.task,
#                         "from_time": from_dt,
#                         "to_time": to_dt,
#                         "hours": item.hours,
#                         "old_progress": item.old_progress or 0,
#                         "change": item.change or 100,
#                         "progress": (float(item.old_progress or 0) + float(item.change or 0)),
#                         "project": item.project or "",
#                     }
#                 )
#                 shift_hours_offset += (item.hours or 0)

#         if tsheet_value["time_logs"] and self.docstatus < 2:
#             frappe.get_doc(tsheet_value).insert(ignore_permissions=True)
#             frappe.db.commit()

#     def validate_timesheet(self, task, date_):
#         existing_timesheet = False
#         timesheet = frappe.db.get_all(
#             "Timesheet",
#             fields=["name"],
#             filters={
#                 "employee": self.employee,
#                 "docstatus": ["<", 2],
#                 "start_date": ["<=", date_],
#                 "end_date": [">=", date_],
#             },
#         )
#         for e_ts in timesheet:
#             details = frappe.db.get_all(
#                 "Timesheet Detail",
#                 fields=["parent", "task", "from_time", "to_time"],
#                 filters={"docstatus": ["<", 2], "parent": e_ts["name"], "task": task},
#             )
#             for d_ts in details:
#                 if getdate(d_ts["from_time"]) == getdate(date_):
#                     existing_timesheet = True
#                     return existing_timesheet
#         return existing_timesheet


# def create_leave_ledger_entry(ref_doc, args, submit=True):
#     ledger = frappe._dict(
#         doctype="Leave Ledger Entry",
#         employee=ref_doc.employee,
#         employee_name=ref_doc.employee_name,
#         transaction_type=ref_doc.doctype,
#         transaction_name=ref_doc.name,
#         is_carry_forward=0,
#         is_expired=0,
#         is_lwp=0,
#     )
#     ledger.update(args)

#     if submit:
#         doc = frappe.get_doc(ledger)
#         doc.flags.ignore_permissions = 1
#         doc.submit()
#     else:
#         delete_ledger_entry(ledger)


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


# @frappe.whitelist()
# def get_task_list(employee=False):
#     user_id = frappe.db.get_value("Employee", {"employee": employee}, "user_id")
#     task_list = frappe.db.get_all(
#         "Task",
#         fields=[
#             "name",
#             "subject",
#             "project",
#             "status",
#             "task_weight",
#             "owner",
#             "exp_start_date",
#             "exp_end_date",
#             "expected_time",
#             "progress",
#         ],
#         filters={"owner": user_id, "status": ["not in", ["Completed", "Cancelled"]]},
#     )
#     return task_list


# @frappe.whitelist()
# def get_checkin_type(employee=False):
#     return frappe.db.get_value("Employee", {"employee": employee}, "check_in_require")


# @frappe.whitelist()
# def get_policy(employee=None, doctype=None, leave_type=None, company=None, from_date=None, to_date=None):
#     total_leave_days = 0.0
#     if employee and from_date and to_date:
#         from_date = getdate(from_date)
#         to_date = getdate(to_date)
#         no_holidays = len(get_holiday_dates_for_employee(employee, from_date, to_date))
#         total_leave_days = float(date_diff(to_date, from_date) + 1 - no_holidays)

#     policy = []
#     # Try combinations: company -> '', None and leave_type -> leave_type -> ''
#     for comp in [company, "", None]:
#         for lt in [leave_type, ""]:
#             for lim in [["<=", total_leave_days], ["in", ["", 0]]]:
#                 pol_filters = {
#                     "lower_limit": ["<", total_leave_days],
#                     "upper_limit": lim,
#                     "doc_type": doctype,
#                     "company": comp,
#                     "leave_type": lt,
#                 }
#                 policy = frappe.get_all(
#                     "Approve Channels Policy", filters=pol_filters, fields=["name"], limit=1
#                 )
#                 if policy:
#                     return policy
#     return policy


# def _combine_datetime(d, t):
#     """Helper: combine date and time into datetime safely."""
#     if isinstance(d, datetime):
#         d = d.date()
#     return datetime.combine(d, t or time(0, 0))


# @frappe.whitelist()
# def get_shift_type(employee=None, from_date=None, to_date=None, half_day=None, half_day_date=None, half_shift=None):
#     """Return start/end time & datetime for (half) shift of an employee on given date range."""
#     shift_time = {}

#     # Resolve default shift
#     shift_type = None
#     emp_shift = frappe.db.get_all(
#         "Employee", filters={"employee": employee}, fields=["default_shift"], limit=1
#     )
#     if emp_shift:
#         shift_type = emp_shift[0]["default_shift"]

#     # Half-shift for a single day
#     if employee and half_day_date and half_shift:
#         half_day_date = getdate(half_day_date)
#         sa = frappe.db.get_all(
#             "Shift Assignment",
#             fields=["shift_type"],
#             filters={
#                 "employee": employee,
#                 "status": "Active",
#                 "docstatus": 1,
#                 "start_date": ["<=", half_day_date],
#                 "end_date": [">=", half_day_date],
#             },
#             limit=1,
#         )
#         if sa:
#             shift_type = sa[0]["shift_type"]

#         st = frappe.db.get_all(
#             "Shift Type",
#             filters={"name": shift_type},
#             fields=["start_time", "end_time", "total_time", "end_next_day"],
#             limit=1,
#         )
#         if not st:
#             return {}

#         st = st[0]
#         start_time = _combine_datetime(half_day_date, st["start_time"])
#         end_time_full = (
#             _combine_datetime(half_day_date, st["end_time"])
#             if not st["end_next_day"]
#             else _combine_datetime(half_day_date + relativedelta(days=1), st["end_time"])
#         )
#         half_hours = (st["total_time"] or 8) / 2.0

#         if half_shift == "First half of shift":
#             end_time = start_time + timedelta(hours=half_hours)
#         else:  # "Second half of shift"
#             end_time = end_time_full
#             start_time = end_time - timedelta(hours=half_hours)

#         shift_time.update(
#             {
#                 "start_time": start_time.time(),
#                 "end_time": end_time.time(),
#                 "start_datetime": start_time,
#                 "end_datetime": end_time,
#             }
#         )
#         return shift_time

#     # Full range
#     if employee and from_date and to_date:
#         from_date = getdate(from_date)
#         to_date = getdate(to_date)

#         sa = frappe.db.get_all(
#             "Shift Assignment",
#             fields=["shift_type"],
#             filters={
#                 "employee": employee,
#                 "status": "Active",
#                 "docstatus": 1,
#                 "start_date": ["<=", from_date],
#                 "end_date": [">=", from_date],
#             },
#             limit=1,
#         )
#         if sa:
#             shift_type = sa[0]["shift_type"]

#         st = frappe.db.get_all(
#             "Shift Type",
#             filters={"name": shift_type},
#             fields=["start_time", "end_time", "total_time", "end_next_day"],
#             limit=1,
#         )
#         if not st:
#             return {}

#         st = st[0]
#         start_time = _combine_datetime(from_date, st["start_time"])
#         end_time = (
#             _combine_datetime(to_date, st["end_time"])
#             if not st["end_next_day"]
#             else _combine_datetime(to_date + relativedelta(days=1), st["end_time"])
#         )

#         shift_time.update(
#             {
#                 "start_time": start_time.time(),
#                 "end_time": end_time.time(),
#                 "start_datetime": start_time,
#                 "end_datetime": end_time,
#             }
#         )
#         return shift_time

#     return {}

# @frappe.whitelist()
# def create_task(values=""):
#     try:
#         values = json.loads(values or "{}")
#         new_task = frappe.new_doc("Task")
#         new_task.subject = values.get("subject")
#         new_task.task_owner = values.get("task_owner")
#         new_task.description = values.get("description")
#         new_task.date = values.get("due_date")
#         new_task.type = values.get("type")
#         new_task.completed_by = values.get("task_owner")
#         new_task.progress = values.get("progress")
#         new_task.insert()
#         return new_task.as_dict()
#     except Exception:
#         return None


# @frappe.whitelist()
# def get_approver(
#     docname="",
#     employee="",
#     doctype="",
#     leave_type="",
#     company="",
#     from_date="",
#     to_date="",
#     leave_approver="",
# ):
#     def has_permission(policy_name, user):
#         emp_des = frappe.db.get_value("Employee", {"user_id": user}, "designation")
#         auth_designations = frappe.db.get_all(
#             "Approve Channels Authorize Designation",
#             filters={"parent": policy_name},
#             pluck="designation",
#         )
#         auth_users = frappe.db.get_all(
#             "Eup User", filters={"parent": policy_name}, pluck="user"
#         )
#         return (user in (auth_users or [])) or (emp_des in (auth_designations or []))

#     def check_permission(policy_name, user):
#         employee_id = frappe.db.get_value("Employee", {"user_id": user}, "employee")
#         while employee_id:
#             user_info = frappe.db.get_value(
#                 "Employee",
#                 {"employee": employee_id},
#                 ["user_id", "designation"],
#                 as_dict=True,
#             )
#             if user_info and user_info.get("user_id") and has_permission(
#                 policy_name, user_info["user_id"]
#             ):
#                 return user_info
#             employee_id = frappe.db.get_value(
#                 "Employee", {"employee": employee_id}, "reports_to"
#             )
#         return False

#     approver = []
#     policy = get_policy(employee, doctype, leave_type, company, from_date, to_date)
#     workflow = get_workflow(doctype)

#     all_approve = 0
#     for state in workflow.states:
#         if state.state == "Approved":
#             all_approve = getattr(state, "all_approve", 0)
#             break

#     if leave_approver:
#         des = frappe.db.get_value(
#             "Employee", {"user_id": leave_approver}, "designation"
#         )
#         approver.append(
#             {
#                 "idx": 1,
#                 "doctype": "Workflow On Doc",
#                 "parent": docname,
#                 "parenttype": "Leave Application",
#                 "parentfield": "workflow",
#                 "user": leave_approver,
#                 "designation": des,
#                 "state": "Approved",
#                 "all_approve": all_approve,
#             }
#         )

#     if policy and not has_permission(policy[0]["name"], leave_approver):
#         user_info = check_permission(policy[0]["name"], leave_approver)
#         if user_info:
#             approver.append(
#                 {
#                     "idx": 2,
#                     "doctype": "Workflow On Doc",
#                     "parent": docname,
#                     "parenttype": "Leave Application",
#                     "parentfield": "workflow",
#                     "user": user_info["user_id"],
#                     "designation": user_info["designation"],
#                     "state": "Approved",
#                     "all_approve": all_approve,
#                 }
#             )

#     return approver

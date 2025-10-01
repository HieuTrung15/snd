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
from frappe.utils.data import get_url_to_form
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs

# from eupapp.eup_hr.doctype.xac_nhan_cham_cong.xac_nhan_cham_cong import update_event
# from eupapp.eupapp.doctype.overrides.workflow import gen_approve_channel


class VntLeaveApplication(LeaveApplication):
    LEAVE_TYPE = "Công tác"
    
    def save(self):
        super().save()
        notify(self, self.employee_name, self.leave_approver)

    def on_submit(self):
        super().on_submit()
        if self.leave_type == self.LEAVE_TYPE:
            self._on_submit_leave_application()
            
			
    def before_submit(self):
        self.status = "Approved"
        
    
    def on_cancel(self):
        super().on_cancel()
        if self.leave_type == self.LEAVE_TYPE:
            self._on_cancel_leave_application()


    # Hook khi submit Leave Application
    def _on_submit_leave_application(self):
        """
        Xử lý tự động tạo Leave Allocation khi submit Leave Application loại "Công tác".
        """
        LEAVE_TYPE = "Công tác"

        
        # Xóa Attendance mặc định nếu employee phiếu không nằm trong items
        leave_employee = self.employee
        items_employees = [emp.employee for emp in self.custom_items]
        if leave_employee not in items_employees:
            attendance_records = frappe.get_all(
                "Attendance",
                filters={
                    "employee": leave_employee,
                    "attendance_date": ["between", [self.from_date, self.to_date]],
                    "status": "On Leave",
                    "leave_type": LEAVE_TYPE
                },
                fields=["name"]
            )
            for ar in attendance_records:
                att_doc = frappe.get_doc("Attendance", ar["name"])
                # if att_doc.docstatus == 1:
                    # Nếu Attendance đã submit, cancel trước
                    # att_doc.cancel()
                # att_doc.delete()
                # frappe.msgprint(f"Cancel default attendance for leave employee {leave_employee} on {att_doc.attendance_date}")
        for emp in self.custom_items:  # bảng nhân viên
            employee = emp.employee
            company = self.company

            for t in self.custom_time_leave:  # bảng thời gian
                from_date = t.from_date
                to_date = t.to_date
                type_leave = t.type_leave

                from_date = getdate(from_date)
                to_date = getdate(to_date)

                # Xác định số ngày yêu cầu
                is_half_day = 1 if type_leave in ["Sáng", "Chiều"] else 0
                half_day_date = from_date + timedelta(days=1) if is_half_day else None


                days_required = 1 if is_half_day else (date_diff(to_date, from_date) + 1)

                # Kiểm tra cấu hình của Leave Type
                leave_type_doc = frappe.get_doc("Leave Type", LEAVE_TYPE)
                allow_over_allocation = leave_type_doc.allow_over_allocation
                # frappe.msgprint(f"allow_over_allocation = {allow_over_allocation}")

                allocation_to_use = None

                if not allow_over_allocation:
                    # ------------------------
                    # Tính tổng ngày đã dùng
                    # ------------------------
                    leaves_taken = 0
                    leave_apps = frappe.get_all(
                        "Leave Application",
                        filters={
                            "employee": employee,
                            "leave_type": LEAVE_TYPE,
                            "status": "Approved",
                            "docstatus": 1,
                        },
                        fields=["from_date", "to_date", "half_day", "half_day_date"],
                    )

                    for la in leave_apps:
                        if la.get("half_day"):
                            leaves_taken += 1
                        else:
                            leaves_taken += date_diff(la["to_date"], la["from_date"]) + 1

                    # ------------------------
                    # Kiểm tra các allocation hiện có
                    # ------------------------
                    allocations = frappe.get_all(
                        "Leave Allocation",
                        filters={
                            "employee": employee,
                            "leave_type": LEAVE_TYPE,
                            "docstatus": 1,
                        },
                        order_by="creation asc",
                        fields=["name", "from_date", "to_date", "total_leaves_allocated"],
                    )
                    balance = 0
                    for a in allocations:
                        a_balance = a["total_leaves_allocated"] - leaves_taken
                        if a_balance >= days_required:
                            allocation_to_use = a["name"]
                            balance = a_balance
                            break
                        balance += a_balance
                    

                    # ------------------------
                    # Nếu không đủ allocation → tạo mới
                    # ------------------------
                    if (not allocation_to_use or balance < days_required) or is_half_day:
                        # Xác định số ngày allocation cần tạo
                        frappe.msgprint(f"is_half_day {is_half_day} {from_date} {to_date}")
                        if is_half_day:
                            # Nửa ngày → tạo allocation 0.5 ngày
                            allocation_days = 1
                            to_date_allocation = from_date + timedelta(days=1)
                        else:
                            # Cả ngày → tạo allocation đủ số ngày nghỉ
                            allocation_days = days_required
                            to_date_allocation = to_date

                        allocation_doc = frappe.new_doc("Leave Allocation")
                        allocation_doc.employee = employee
                        allocation_doc.leave_type = LEAVE_TYPE
                        allocation_doc.from_date = from_date
                        allocation_doc.to_date = to_date_allocation
                        allocation_doc.new_leaves_allocated = allocation_days
                        allocation_doc.total_leaves_allocated = allocation_days
                        allocation_doc.company = company
                        allocation_doc.insert()
                        allocation_doc.submit()

                        allocation_to_use = allocation_doc.name
                    
                day = from_date
        
                while day <= to_date:    
                    attendance_doc = frappe.new_doc("Attendance")
                    attendance_doc.employee = employee
                    attendance_doc.attendance_date = day
                    # attendance_doc.status = "On Leave"
                    attendance_doc.leave_type = "Công tác"

                    # Nếu là nửa ngày, chỉ đánh dấu nửa ngày đúng ngày half_day_date
                    if is_half_day:
                        attendance_doc.status = "Half Day"
                    else:
                        attendance_doc.status = "On Leave"
                    attendance_doc.insert()
                    attendance_doc.submit()
                    day += timedelta(days=1)





    def _on_cancel_leave_application(self):
        """Xử lý khi cancel Leave Application loại Công tác."""
        leave_type = "Công tác"
        if self.leave_type != leave_type:
            return

        for emp in self.custom_items:  # bảng nhân viên
            employee = emp.employee

            for t in self.custom_time_leave:  # bảng thời gian
                from_date = t.from_date
                to_date = t.to_date

                # -------------------------
                # Xoá các bản ghi Attendance tương ứng
                # -------------------------
                attendance_records = frappe.get_all(
                    "Attendance",
                    filters={
                        "employee": employee,
                        "attendance_date": ["between", [from_date, to_date]],
                        "leave_type": leave_type,
                        "status": ["in", ["On Leave", "Half Day"]]
                    },
                    fields=["name"]
                )
                for ar in attendance_records:
                    attendance_doc = frappe.get_doc("Attendance", ar["name"])
                    if attendance_doc.docstatus == 1:
                        attendance_doc.cancel()
                    # attendance_doc.delete()
                    frappe.msgprint(
                        f"Attendance record deleted for {employee} on {attendance_doc.attendance_date}"
                    )
                # -------------------------
                # Hủy Leave Allocation tự tạo nếu có
                # -------------------------
                allocations = frappe.get_all(
                    "Leave Allocation",
                    filters={
                        "employee": employee,
                        "leave_type": leave_type,
                        "from_date": ["<=", to_date],
                        "to_date": [">=", from_date],
                        "docstatus": 1
                    },
                    fields=["name"]
                )
                for alloc in allocations:
                    allocation_doc = frappe.get_doc("Leave Allocation", alloc["name"])
                    allocation_doc.cancel()

    


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


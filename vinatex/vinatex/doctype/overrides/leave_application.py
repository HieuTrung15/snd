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
            
			
    def before_submit(self):
        self.status = "Approved"

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


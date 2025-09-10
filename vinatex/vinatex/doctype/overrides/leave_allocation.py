# Copyright (c) 2015,
# Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import flt, getdate

from hrms.hr.doctype.leave_allocation.leave_allocation import (
    LeaveAllocation,
    get_carry_forwarded_leaves,
)
from hrms.hr.doctype.leave_ledger_entry.leave_ledger_entry import expire_allocation


class OverlapError(frappe.ValidationError):
    pass


class BackDatedAllocationError(frappe.ValidationError):
    pass


class OverAllocationError(frappe.ValidationError):
    pass


class LessAllocationError(frappe.ValidationError):
    pass


class ValueMultiplierError(frappe.ValidationError):
    pass


class VntLeaveAllocation(LeaveAllocation):
    def on_submit(self):
        self.create_leave_ledger_entry()
        allocation = get_previous_allocation(self.from_date, self.leave_type, self.employee)
        if self.carry_forward and allocation:
            # Giữ nguyên cách gọi theo code gốc (truyền record prev allocation)
            expire_allocation(allocation)

    # @frappe.whitelist()
    # def set_total_leaves_allocated(self):
    #     # Số phép chưa dùng mang sang (tuỳ theo flag carry_forward)
    #     self.unused_leaves = get_carry_forwarded_leaves(
    #         self.employee, self.leave_type, self.from_date, self.carry_forward
    #     )

    #     unused_leaves_expired_month = frappe.db.get_value(
    #         "Leave Type",
    #         {"name": self.leave_type},
    #         "custom_expired_month_of_unused_leaves",
    #     )

    #     if not self.old_leaves_allocated:
    #         self.old_leaves_allocated = 0

    #     # Rule custom theo tháng hết hạn & loại phép
    #     if (
    #         unused_leaves_expired_month
    #         and getdate(self.from_date).month == int(unused_leaves_expired_month)
    #         and self.leave_type == Config.LEAVE_TYPE
    #     ):
    #         if self.unused_leaves >= (Config.CUMULATIVE_MONTHS[-1]):
    #             # Giới hạn unused theo tháng hết hạn (logic custom của bạn)
    #             self.unused_leaves = min(
    #                 self.unused_leaves, int(unused_leaves_expired_month) - 1
    #             )
    #             self.old_leaves_allocated = 0

    #         self.total_leaves_allocated = flt(self.unused_leaves) + flt(self.new_leaves_allocated)
    #     else:
    #         self.total_leaves_allocated = flt(self.unused_leaves) + flt(self.new_leaves_allocated)

    #     # Áp trần theo Leave Type nếu có
    #     self.limit_carry_forward_based_on_max_allowed_leaves()

    #     # Ghi lại thông tin CF ở allocation trước đó (nếu dùng core method này)
    #     if self.carry_forward:
    #         self.set_carry_forwarded_leaves_in_previous_allocation()

    #     # Yêu cầu tổng cấp bắt buộc với non-earned, non-compensatory
    #     if (
    #         not self.total_leaves_allocated
    #         and not frappe.db.get_value("Leave Type", self.leave_type, "is_earned_leave")
    #         and not frappe.db.get_value("Leave Type", self.leave_type, "is_compensatory")
    #     ):
    #         frappe.throw(
    #             _("Total leaves allocated is mandatory for Leave Type {0}").format(self.leave_type)
    #         )


def get_previous_allocation(from_date, leave_type, employee):
    """Lấy allocation liền trước theo to_date (đã submit) của cùng nhân viên & leave type."""
    rows = frappe.get_all(
        "Leave Allocation",
        filters={
            "to_date": ("<", from_date),
            "leave_type": leave_type,
            "employee": employee,
            "docstatus": 1,
        },
        fields=[
            "name",
            "from_date",
            "to_date",
            "employee",
            "leave_type",
            "total_leaves_allocated",
            "old_leaves_allocated",
        ],
        order_by="to_date desc",
        limit=1,
        as_list=False,
    )
    return rows[0] if rows else None


class Config:
    LEAVE_TYPE = "Nghỉ phép năm"
    HOLIDAY_LIST = "Tiêu chuẩn 2025"
    LEAVE_POLICY_TITLE = "Nghỉ phép năm"
    COMPANY = "TẬP ĐOÀN DỆT MAY VIỆT NAM"
    CUMULATIVE_MONTHS = [1, 2, 3]

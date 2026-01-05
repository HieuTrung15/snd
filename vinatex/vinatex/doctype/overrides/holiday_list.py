from __future__ import unicode_literals


import frappe
from datetime import date
import calendar
from frappe.utils import getdate, now_datetime
from dateutil.relativedelta import relativedelta
from erpnext.setup.doctype.holiday_list.holiday_list import (
    HolidayList
)


class VntHolidayList(HolidayList):
    def after_insert(doc, method=None):
        """
        Khi Holiday List vừa được tạo:
        - Set default_holiday_list cho TẤT CẢ Company
        - Set holiday_list cho TẤT CẢ Employee có status = Active
        """

        holiday_list = doc.name
        # 1) Update tất cả Company
        frappe.db.sql(
            """
            UPDATE `tabCompany`
            SET default_holiday_list = %(hl)s
            WHERE default_holiday_list IS NOT NULL
            """,
            {"hl": holiday_list},
        )

        # 2) Update tất cả Employee đang Active
        frappe.db.sql(
            """
            UPDATE `tabEmployee`
            SET holiday_list = %(hl)s
            WHERE status = 'Active'
            AND docstatus < 2
            """,
            {"hl": holiday_list},
        )

        frappe.db.commit()

# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Dict, List

import frappe
from frappe import _
from frappe.model.document import Document


class VNTRecurringExtraBenefit(Document):
	@frappe.whitelist()
	def get_emp_list(self):
		"""Return employees that have the selected allowance type on their profile."""
		if not self.type:
			frappe.throw(_("Vui lòng chọn Loại phụ cấp trước khi lấy danh sách nhân sự."))

		rows = _get_employees_with_allowance(self.type)
		return {"items": rows}


def _get_employees_with_allowance(allowance_type: str) -> List[Dict]:
	"""Fetch active employees and allowance values for the given allowance type."""
	allowance_rows = frappe.db.get_all(
		"VNT Employee Allowance Type",
		filters={
			"type": allowance_type,
			"parenttype": "Employee",
			"parentfield": "custom_phu_cap",
		},
		fields=[
			"parent as employee",
			"type",
			"he_so",
			"so_tien_phu_cap",
			"from_date",
			"to_date",
			"creation",
		],
		order_by="from_date desc, creation desc",
		limit_page_length=0,
	)

	if not allowance_rows:
		return []

	latest_allowance = {}
	for row in allowance_rows:
		employee_code = row.get("employee")
		if not employee_code or employee_code in latest_allowance:
			continue
		latest_allowance[employee_code] = row

	if not latest_allowance:
		return []

	employee_codes = list(latest_allowance.keys())
	employees = frappe.get_all(
		"Employee",
		filters={"name": ("in", employee_codes), "status": "Active"},
		fields=["name", "employee_name", "designation"],
		limit_page_length=0,
	)

	result = []
	for emp in employees:
		allowance = latest_allowance.get(emp.name)
		if not allowance:
			continue
		result.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"designation": emp.designation,
				"allowance_type": allowance.get("type"),
				"he_so": allowance.get("he_so"),
				"amount": allowance.get("so_tien_phu_cap"),
				"from_date": allowance.get("from_date"),
				"to_date": allowance.get("to_date"),
			}
		)

	result.sort(key=lambda d: (d.get("employee_name") or d.get("employee") or ""))
	return result

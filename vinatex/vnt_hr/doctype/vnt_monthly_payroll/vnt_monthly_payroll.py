# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTMonthlyPayroll(Document):
	pass


@frappe.whitelist()
def compute_item(employee, company, payroll_month, payroll_year):
	salary_parameter = frappe.get_doc("VNT Salary Parameter", {filters={
		"from_date": payroll_year + "-" + str(payroll_month).zfill(2) + "-01",
		"to_date": company,
		"payroll_month": payroll_month,
		"payroll_year": payroll_year,
	}})
	return salary_parameter.compute_payroll_items()
# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTExternalProducts(Document):
	pass


@frappe.whitelist()
def get_employee_name(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "name", as_dict=True)
	return employee_doc.name if employee_doc else ""


@frappe.whitelist()
def get_reports_to(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "department", as_dict=True)
	if not employee_doc:
		return
	approver = frappe.get_value("Department Approver", {"parent": employee_doc.department, "custom_level_1": True}, "approver", as_dict=True)
	if approver:
		approver_emp = frappe.get_value("Employee", {"user_id": approver.approver}, ["name", "employee_name"])
	return approver_emp if approver else ""
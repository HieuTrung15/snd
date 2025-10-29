# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTCourierRegistration(Document):
	pass


@frappe.whitelist()
def get_employee_name(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "name", as_dict=True)
	return employee_doc.name if employee_doc else ""


@frappe.whitelist()
def get_reports_to(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "department", as_dict=True)
	if employee_doc.department:
		approver = frappe.get_value("Department Approver", {"parent": employee_doc.department, "custom_level_1": True}, "approver", as_dict=True)
		if approver:
			approver_name = frappe.get_value("Employee", {"user_id": approver.approver}, "name", as_dict=True)
			return approver_name.name if approver_name else ""
	return ""


@frappe.whitelist()
def get_supplier_address(supplier):
	addr_name = frappe.get_value("Supplier", {"name": supplier, "is_transporter": 1}, "supplier_primary_address", as_dict=True)
	if addr_name:
		address = frappe.get_value("Address", {"name": addr_name.supplier_primary_address}, "address_line1", as_dict=True)
		if address:
			return address.address_line1
	return ""
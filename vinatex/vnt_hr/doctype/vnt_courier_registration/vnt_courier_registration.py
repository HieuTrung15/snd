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
			approver_name = frappe.get_value("Employee", {"user_id": approver.approver}, "employee_name", as_dict=True)
			return approver_name.employee_name if approver_name else ""
	return ""


@frappe.whitelist()
def get_supplier_address(supplier):
	addr_name = frappe.get_value("Supplier", {"name": supplier, "is_transporter": 1}, "supplier_primary_address", as_dict=True)
	if addr_name:
		address = frappe.get_value("Address", {"name": addr_name.supplier_primary_address}, "address_line1", as_dict=True)
		if address:
			return address.address_line1
	return ""

@frappe.whitelist()
def get_courier_items():
    """
    Trả về list các dòng bưu gửi (đã flatten) để render bảng.
    Mỗi dòng = 1 người nhận trong child + thông tin chung từ parent.
    Chỉ trả các bản ghi mà user hiện tại được phép xem.
    """

    parent_doctype = "VNT Courier Registration"
    child_doctype  = "VNT Courier Registration Item"

    user = frappe.session.user

    parent_filters = {}  # <-- filter phân quyền

    parent_fields = [
        "name",
        "date",
        "employee",
        "qty",
        "package_type",
        "type_send",
        "bao_phat",
		"code_follow"
    ]

    parents = frappe.get_all(
        parent_doctype,
        filters=parent_filters,
        fields=parent_fields,
        order_by="date desc",
        limit_page_length=200,
    )

    all_rows = []

    for pr in parents:
        child_rows = frappe.get_all(
            child_doctype,
            filters={"parent": pr["name"]},
            fields=[
                "receiver",
                "phone",
                "addr",
            ],
            limit_page_length=500,
        )

        for ch in child_rows:
            all_rows.append({
                "date_text": pr.get("date", "") or "",
                "sender_employee": pr.get("employee", "") or "",
                "receiver": ch.get("receiver", "") or "",
                "address": ch.get("addr", "") or "",
                "phone": ch.get("phone", "") or "",
                "qty": pr.get("qty", "") or "",
                "package_type": pr.get("package_type", "") or "",
                "type_send": pr.get("type_send", "") or "",
                "bao_phat": pr.get("bao_phat", "") or "",
				"code_follow": pr.get("code_follow", "") or "",
            })

    return all_rows

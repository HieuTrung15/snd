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
	department = employee_doc.department if employee_doc else None
	if department:
		approver = frappe.get_value("Department Approver", {"parent": department, "custom_level_1": True}, "approver", as_dict=True)
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

import frappe

@frappe.whitelist()
def get_courier_items():
    """
    Tạo bảng lịch sử chuyển phát nhanh
    - Trả về dạng flatten: 1 parent có nhiều child -> nhiều dòng
    - Mỗi dòng có `name` (parent name) để JS click mở đúng document
    """

    parent_doctype = "VNT Courier Registration"
    child_doctype = "VNT Courier Registration Item"

    parent_filters = {}

    parent_fields = [
        "name",
        "date",
        "employee",
        "qty",
        "package_type",
        "type_send",
        "bao_phat",
        "code_follow",
        "note",  # thêm field note
    ]

    parents = frappe.get_all(
        parent_doctype,
        filters=parent_filters,
        fields=parent_fields,
        order_by="date desc",
        limit_page_length=200,
    )

    if not parents:
        return []

    parent_by_name = {p["name"]: p for p in parents}
    parent_names = list(parent_by_name.keys())

    children = frappe.get_all(
        child_doctype,
        filters={"parent": ["in", parent_names]},
        fields=["parent", "receiver", "phone", "addr"],
        order_by="idx asc",
        limit_page_length=5000,
    )

    emp_codes = sorted({(p.get("employee") or "").strip() for p in parents if p.get("employee")})
    emp_name_map = {}

    if emp_codes:
        emp_rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", emp_codes]},
            fields=["name", "employee_name"],
            limit_page_length=len(emp_codes) + 10,
        )
        emp_name_map = {
            e["name"]: (e.get("employee_name") or e["name"])
            for e in emp_rows
        }

    def get_sender_name(emp_code):
        if not emp_code:
            return ""
        emp_code = emp_code.strip()
        return emp_name_map.get(emp_code) or emp_code

    children_by_parent = {}
    for ch in children:
        children_by_parent.setdefault(ch["parent"], []).append(ch)

    all_rows = []

    for parent_name in parent_names:
        pr = parent_by_name[parent_name]
        sender_name = get_sender_name(pr.get("employee"))
        ch_list = children_by_parent.get(parent_name) or []

        if not ch_list:
            all_rows.append({
                "name":            parent_name,
                "date_text":       pr.get("date") or "",
                "sender_employee": sender_name or "",
                "receiver":        "",
                "address":         "",
                "phone":           "",
                "qty":             pr.get("qty") or "",
                "package_type":    pr.get("package_type") or "",
                "type_send":       pr.get("type_send") or "",
                "bao_phat":        pr.get("bao_phat") or "",
                "code_follow":     pr.get("code_follow") or "",
                "note":            pr.get("note") or "",
            })
            continue

        for ch in ch_list:
            all_rows.append({
                "name":            parent_name,
                "date_text":       pr.get("date") or "",
                "sender_employee": sender_name or "",
                "receiver":        ch.get("receiver") or "",
                "address":         ch.get("addr") or "",
                "phone":           ch.get("phone") or "",
                "qty":             pr.get("qty") or "",
                "package_type":    pr.get("package_type") or "",
                "type_send":       pr.get("type_send") or "",
                "bao_phat":        pr.get("bao_phat") or "",
                "code_follow":     pr.get("code_follow") or "",
                "note":            pr.get("note") or "",
            })

    return all_rows

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

@frappe.whitelist()
def get_courier_items():
    """
	Tạo bảng lịch sử chuyển phát nhanh
    """

    parent_doctype = "VNT Courier Registration"
    child_doctype  = "VNT Courier Registration Item"

    current_user = frappe.session.user

    # Nếu muốn giới hạn theo người tạo / quyền xem:
    parent_filters = {
        # ví dụ chỉ cho xem phiếu mình tạo:
        # "owner": current_user
    }

    parent_fields = [
        "name",
        "date",         
        "employee",      
        "qty",
        "package_type",
        "type_send",
        "bao_phat",
        "code_follow",
    ]

    parents = frappe.get_all(
        parent_doctype,
        filters=parent_filters,
        fields=parent_fields,
        order_by="date desc",
        limit_page_length=200,
        # ignore_permissions=True,
    )

    emp_name_cache = {}

    def get_employee_name(emp_code):
        """ Employee.employee_name"""
        if not emp_code:
            return ""

        if emp_code in emp_name_cache:
            return emp_name_cache[emp_code]

        emp_doc = frappe.db.get_value(
            "Employee",
            emp_code, 
            ["employee_name"],
            as_dict=True,
        )

        if emp_doc and emp_doc.get("employee_name"):
            emp_name_cache[emp_code] = emp_doc["employee_name"]
        else:
            # fallback
            emp_name_cache[emp_code] = emp_code

        return emp_name_cache[emp_code]

    all_rows = []

    for pr in parents:
        # tra tên nhân viên gửi từ mã employee
        sender_name = get_employee_name(pr.get("employee"))

        # lấy child rows (người nhận / địa chỉ / sđt)
        child_rows = frappe.get_all(
            child_doctype,
            filters={"parent": pr["name"]},
            fields=[
                "receiver",   # tên người nhận
                "phone",      # sđt người nhận
                "addr",       # địa chỉ người nhận
            ],
            limit_page_length=500,
            # ignore_permissions=True 
        )

        for ch in child_rows:
            all_rows.append({
                "date_text":       pr.get("date", "") or "",
                "sender_employee": sender_name or "",    
                "receiver":        ch.get("receiver", "") or "",
                "address":         ch.get("addr", "") or "",
                "phone":           ch.get("phone", "") or "",
                "qty":             pr.get("qty", "") or "",
                "package_type":    pr.get("package_type", "") or "",
                "type_send":       pr.get("type_send", "") or "",
                "bao_phat":        pr.get("bao_phat", "") or "",
                "code_follow":     pr.get("code_follow", "") or "",
            })

    return all_rows

# Copyright (c) 2025
# For license information, please see license.txt

import frappe

TARGET_GROUPS = ("Người quản lý", "Lãnh đạo cấp trung")

def execute(filters=None):
    filters = frappe._dict(filters or {})

    columns = get_columns()
    data = get_data(filters)
    summary = get_report_summary(data, filters)

    # Trả về: columns, data, message(None), chart(None), report_summary
    return columns, data, None, None, summary


def get_columns():
    return [
        {"label": "Công ty", "fieldname": "company", "fieldtype": "Data", "options": "Company", "width": 160},
        {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Data", "options": "Employee", "width": 110},
        {"label": "Họ và tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "options": "Department", "width": 160},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Data", "options": "Designation", "width": 160},
        {"label": "Nhóm chức danh", "fieldname": "custom_designation_group", "fieldtype": "Data", "options": "VNT Designation Group", "width": 180},
        {"label": "Loại HĐLĐ", "fieldname": "employment_type", "fieldtype": "Data", "width": 120},
        {"label": "Trạng thái", "fieldname": "status", "fieldtype": "Data", "width": 90},
        {"label": "Ngày vào", "fieldname": "date_of_joining", "fieldtype": "Date", "width": 110},
        {"label": "Ngày nghỉ", "fieldname": "relieving_date", "fieldtype": "Date", "width": 110},
    ]


def get_data(filters):
    # Xác định tập nhóm cần lọc
    group_mode = (filters.get("group_mode") or "").strip()
    if group_mode == "Người quản lý":
        groups = ("Người quản lý",)
    elif group_mode == "Lãnh đạo cấp trung":
        groups = ("Lãnh đạo cấp trung",)
    else:
        groups = TARGET_GROUPS  # cả hai

    # Base conditions & params
    conditions = ["e.custom_designation_group in %(groups)s"]
    params = {"groups": groups}

    if filters.get("company"):
        conditions.append("e.company = %(company)s")
        params["company"] = filters.company

    if filters.get("department"):
        conditions.append("e.department = %(department)s")
        params["department"] = filters.department

    # Trạng thái
    status = (filters.get("status") or "Active").strip()
    if status != "Tất cả":
        conditions.append("e.status = %(status)s")
        params["status"] = status

    # Tìm nhanh
    if filters.get("search_text"):
        st = f"%{filters.search_text.strip()}%"
        conditions.append(
            "(e.name LIKE %(st)s OR e.employee_name LIKE %(st)s OR e.designation LIKE %(st)s)"
        )
        params["st"] = st

    where = " AND ".join(conditions)

    # Lưu ý: dùng field custom_designation_group trên Employee
    sql = f"""
        SELECT
            e.name AS employee,
            e.employee_name,
            e.company,
            e.department,
            e.designation,
            e.custom_designation_group,
            e.employment_type,
            e.status,
            e.date_of_joining,
            e.relieving_date
        FROM `tabEmployee` e
        WHERE {where}
        AND e.status = 'Active'
        ORDER BY
            FIELD(e.custom_designation_group, 'Người quản lý', 'Lãnh đạo cấp trung'),
            e.department ASC,
            e.employee_name ASC
    """

    return frappe.db.sql(sql, params, as_dict=True)


def get_report_summary(data, filters):
    # Đếm theo nhóm chức danh
    managers = sum(1 for r in data if (r.get("custom_designation_group") == "Người quản lý"))
    middle = sum(1 for r in data if (r.get("custom_designation_group") == "Lãnh đạo cấp trung"))

    total = len(data)

    return [
        {"label": "Tổng", "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": "Người quản lý", "value": managers, "indicator": "Green", "datatype": "Int"},
        {"label": "Lãnh đạo cấp trung", "value": middle, "indicator": "Orange", "datatype": "Int"},
    ]


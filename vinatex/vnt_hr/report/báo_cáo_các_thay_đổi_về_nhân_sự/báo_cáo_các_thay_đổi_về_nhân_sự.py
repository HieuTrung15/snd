# Copyright (c) 2025, vinatex
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today

def execute(filters=None):
    if not filters:
        filters = {}

    # defaults
    if not filters.get("to_date"):
        filters["to_date"] = today()
    if not filters.get("from_date"):
        # mặc định lấy 90 ngày gần đây
        filters["from_date"] = frappe.utils.add_days(filters["to_date"], -90)

    # validate
    if getdate(filters["from_date"]) > getdate(filters["to_date"]):
        frappe.throw("Từ ngày không được lớn hơn Đến ngày.")

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Trạng thái", "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": "Mã", "fieldname": "employee", "fieldtype": "Data", "options": "Employee", "width": 110},
        {"label": "Họ tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Bộ phận", "fieldname": "department", "fieldtype": "Data", "options": "Department", "width": 180},
        {"label": "Vị trí công việc", "fieldname": "designation", "fieldtype": "Data", "width": 180},
        {"label": "Loại", "fieldname": "decision_type_name", "fieldtype": "Data", "width": 220},
        {"label": "Số quyết định", "fieldname": "decision_number", "fieldtype": "Data", "width": 150},
        {"label": "Ngày hiệu lực", "fieldname": "from_date", "fieldtype": "Date", "width": 120},
        {"label": "Hiệu lực đến hết ngày", "fieldname": "to_date", "fieldtype": "Date", "width": 150},
        {"label": "Đơn vị ban hành (header)", "fieldname": "header_department", "fieldtype": "Data", "width": 180},
        {"label": "Ghi chú (item)", "fieldname": "item_note", "fieldtype": "Data", "width": 200},
        {"label": "Số QĐ (header)", "fieldname": "decision_name", "fieldtype": "Data", "options": "VNT Decision", "width": 150},
    ]


def get_data(filters):
    # where clause + params (chống injection)
    wh = []
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    # chỉ lấy đã phê duyệt mặc định
    only_approved = frappe.utils.cint(filters.get("only_approved", 1))
    if only_approved:
        wh.append("d.docstatus = 1")
    else:
        # nếu cần cả nháp/hủy thì bỏ lọc, nhưng vẫn hiển thị trạng thái
        pass

    # lọc theo hiệu lực (d.from_date trong khoảng) – có thể đổi sang d.date nếu bạn muốn lọc theo ngày ký
    wh.append("d.from_date BETWEEN %(from_date)s AND %(to_date)s")

    # lọc loại quyết định
    if filters.get("decision_type"):
        # decision_type có thể là Link tới VNT Decision Type (name) hoặc text thường
        if isinstance(filters["decision_type"], (list, tuple)):
            placeholders = ", ".join(["%s"] * len(filters["decision_type"]))
            wh.append(f"d.decision_type IN ({placeholders})")
            params.update({f"dt{i}": v for i, v in enumerate(filters["decision_type"])})
            # chuyển lại cho sql params
            params_list = [params[f"dt{i}"] for i in range(len(filters["decision_type"]))]

        else:
            wh.append("d.decision_type = %(decision_type)s")
            params["decision_type"] = filters["decision_type"]
            params_list = []

    else:
        params_list = []

    # lọc phòng ban (theo Employee)
    if filters.get("department"):
        wh.append("e.department = %(department)s")
        params["department"] = filters["department"]

    # lọc công ty (theo Employee)
    if filters.get("company"):
        wh.append("e.company = %(company)s")
        params["company"] = filters["company"]

    # search nhanh theo mã/ tên
    if filters.get("search"):
        wh.append("(di.employee LIKE %(kw)s OR COALESCE(di.employee_name, e.employee_name) LIKE %(kw)s)")
        params["kw"] = f"%{filters['search']}%"

    where_sql = (" AND ".join(wh)) if wh else "1=1"

    # ghép sql
    sql = f"""
        SELECT
            -- trạng thái
            CASE d.docstatus
                WHEN 0 THEN 'Nháp'
                WHEN 1 THEN 'Phê duyệt'
                WHEN 2 THEN 'Hủy'
                ELSE 'Khác'
            END AS status,

            -- nhân viên
            di.employee AS employee,
            COALESCE(di.employee_name, e.employee_name) AS employee_name,
            COALESCE(e.department, d.department) AS department,
            COALESCE(di.designation, e.designation) AS designation,

            -- loại quyết định
            COALESCE(dt.decision_type, d.decision_type) AS decision_type_name,

            -- thông tin quyết định (header)
            d.decision_number,
            d.from_date,
            d.to_date,
            d.department AS header_department,
            d.name AS decision_name,

            -- ghi chú ở item (nếu có)
            di.note AS item_note

        FROM `tabVNT Decision` d
        INNER JOIN `tabVNT Decision Item` di
            ON di.parent = d.name AND di.parenttype = 'VNT Decision'
        LEFT JOIN `tabEmployee` e
            ON e.name = di.employee
        LEFT JOIN `tabVNT Decision Type` dt
            ON dt.name = d.decision_type
        WHERE {where_sql}
        ORDER BY d.from_date DESC, d.name DESC, di.idx ASC
    """

    # ghép params theo IN 
    if params_list:
        # frappe.db.sql không nhận dict + LIST cho IN mixing đơn giản, nên tách thủ công:
        # build full params tuple theo thứ tự: params dict trước, rồi các item cho IN
        base_params = tuple(params.get(k) for k in params if not k.startswith("dt"))
        full_params = base_params + tuple(params_list)
        rows = frappe.db.sql(sql, full_params, as_dict=True)
    else:
        rows = frappe.db.sql(sql, params, as_dict=True)

    return rows

import frappe
from frappe.utils import flt, cstr, getdate

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        # {"label": "STT", "fieldname": "stt", "fieldtype": "Int", "width": 40},
        {"label": "Mã nhân viên", "fieldname": "ma_nv", "fieldtype": "Data", "width": 120},
        {"label": "Họ và tên", "fieldname": "ho_ten", "fieldtype": "Data", "width": 200},
        {"label": "Ngày sinh", "fieldname": "ngay_sinh", "fieldtype": "Date", "width": 120},
        {"label": "Giới tính", "fieldname": "gioi_tinh", "fieldtype": "Data", "width": 80},
        {"label": "Chức vụ trước khi nghỉ hưu", "fieldname": "chuc_vu", "fieldtype": "Data", "width": 200},
        {"label": "Ngày nghỉ hưu", "fieldname": "ngay_nghi_huu", "fieldtype": "Date", "width": 120},
        {"label": "Địa chỉ liên hệ", "fieldname": "dia_chi", "fieldtype": "Data", "width": 300},
        {"label": "Điện thoại liên lạc", "fieldname": "dien_thoai", "fieldtype": "Data", "width": 140},
    ]

    conditions = ["status = 'Left'"]   # chỉ nhân viên đã nghỉ
    values = {}

    # lọc theo công ty
    if filters.get("company"):
        conditions.append("company = %(company)s")
        values["company"] = filters["company"]

    # lọc theo phòng ban
    if filters.get("department"):
        conditions.append("department = %(department)s")
        values["department"] = filters["department"]

    # lọc theo ngày nghỉ hưu từ
    if filters.get("retirement_from"):
        conditions.append("(relieving_date >= %(retirement_from)s OR date_of_retirement >= %(retirement_from)s)")
        values["retirement_from"] = filters["retirement_from"]

    # lọc theo ngày nghỉ hưu đến
    if filters.get("retirement_to"):
        conditions.append("(relieving_date <= %(retirement_to)s OR date_of_retirement <= %(retirement_to)s)")
        values["retirement_to"] = filters["retirement_to"]

    # loc theo tên nhân viên
    if filters.get("employee_name"):
        conditions.append("employee_name LIKE %(employee_name)s")
        values["employee_name"] = "%" + filters["employee_name"] + "%"

    # gộp conditions thành 1 string
    condition_str = " AND ".join(conditions)

    employees = frappe.db.sql(f"""
        SELECT
            name AS ma_nv,
            employee_name AS ho_ten,
            date_of_birth AS ngay_sinh,
            gender AS gioi_tinh,
            designation AS chuc_vu,
            COALESCE(date_of_retirement, relieving_date) AS ngay_nghi_huu,
            permanent_address AS dia_chi,
            COALESCE(cell_number) AS dien_thoai
        FROM `tabEmployee`
        WHERE {condition_str}
        ORDER BY ngay_nghi_huu ASC
    """, values=values, as_dict=True)

    data = []
    for idx, e in enumerate(employees, start=1):
        # e["stt"] = idx
        data.append(e)

    return columns, data


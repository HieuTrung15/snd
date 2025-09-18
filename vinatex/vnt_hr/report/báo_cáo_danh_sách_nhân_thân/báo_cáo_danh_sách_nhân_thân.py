import frappe
from frappe.utils.data import getdate, today

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    return [
        {"label": "Mã số NV", "fieldname": "employee_code", "fieldtype": "Data", "width": 120},
        {"label": "Họ và tên Nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
        {"label": "Họ và tên Nhân thân", "fieldname": "relative_name", "fieldtype": "Data", "width": 150},
        {"label": "Quốc tịch", "fieldname": "nationality", "fieldtype": "Data", "width": 100},
        {"label": "Mối quan hệ", "fieldname": "relationship", "fieldtype": "Data", "width": 100},
        {"label": "Giới tính", "fieldname": "gender", "fieldtype": "Data", "width": 80},
        {"label": "Năm sinh", "fieldname": "dob", "fieldtype": "Data", "width": 100},
        {"label": "Người phụ thuộc", "fieldname": "dependent", "fieldtype": "Check", "width": 100},

        # Placeholder các cột còn lại
        {"label": "Hiện đang đăng ký NPT tại Vinatex", "fieldname": "registered_at_vinatex", "fieldtype": "Check", "width": 150},
        {"label": "Mã số thuế NPT", "fieldname": "tax_code", "fieldtype": "Data", "width": 120},
        {"label": "Quê quán - Tỉnh/Thành phố", "fieldname": "hometown_city", "fieldtype": "Data", "width": 120},
        {"label": "Quê quán - Phường/Xã/Đặc khu", "fieldname": "hometown_ward", "fieldtype": "Data", "width": 120},
        {"label": "Nghề nghiệp", "fieldname": "occupation", "fieldtype": "Data", "width": 120},
        {"label": "Nơi ở - Tỉnh/Thành phố", "fieldname": "residence_city", "fieldtype": "Data", "width": 120},
        {"label": "Nơi ở - Phường/Xã/Đặc khu", "fieldname": "residence_ward", "fieldtype": "Data", "width": 120},
        {"label": "Số nhà", "fieldname": "house_no", "fieldtype": "Data", "width": 80},
        {"label": "Địa chỉ đầy đủ", "fieldname": "full_address", "fieldtype": "Data", "width": 200},
        {"label": "Đã mất", "fieldname": "deceased", "fieldtype": "Check", "width": 80},
    ]

def get_data(filters):
    conditions = []
    if filters.get("employee"):
        conditions.append(f"emp.name = '{filters.get('employee')}'")
    if filters.get("department"):
        conditions.append(f"emp.department = '{filters.get('department')}'")

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = " AND " + where_clause

    sql = f"""
        SELECT
            emp.name AS employee_code,
            emp.employee_name
        FROM
            `tabEmployee` emp
        WHERE 1=1 {where_clause}
    """

    data = frappe.db.sql(sql, as_dict=True)

    # Thêm placeholder cho các cột chưa có data
    for d in data:
        d["registered_at_vinatex"] = ""
        d["tax_code"] = ""
        d["hometown_city"] = ""
        d["hometown_ward"] = ""
        d["occupation"] = ""
        d["residence_city"] = ""
        d["residence_ward"] = ""
        d["house_no"] = ""
        d["full_address"] = ""
        d["deceased"] = ""

    return data

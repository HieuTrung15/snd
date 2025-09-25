import frappe
from frappe.utils.data import getdate, today

CHILD_TABLE = "VNT Employee Tax"  # Đổi lại nếu tên doctype khác

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

        # Thông tin nhân thân (từ bảng con)
        {"label": "Họ và tên Nhân thân", "fieldname": "relative_name", "fieldtype": "Data", "width": 150},
        {"label": "Quốc tịch", "fieldname": "nationality", "fieldtype": "Data", "width": 100},
        {"label": "Mối quan hệ", "fieldname": "relationship", "fieldtype": "Data", "width": 120},
        {"label": "Giới tính", "fieldname": "gender", "fieldtype": "Data", "width": 80},
        {"label": "Năm sinh / Ngày sinh", "fieldname": "dob", "fieldtype": "Data", "width": 140},
        {"label": "Người phụ thuộc", "fieldname": "dependent", "fieldtype": "Check", "width": 120},
        {"label": "MST Nhân thân", "fieldname": "tax_code", "fieldtype": "Data", "width": 140},
        {"label": "Đang đăng ký NPT tại Vinatex", "fieldname": "registered_at_vinatex", "fieldtype": "Check", "width": 180},

        # Placeholder các cột địa chỉ/nghề nghiệp (nếu sau này có field ở child table thì map vào)
        {"label": "Quê quán - Tỉnh/Thành phố", "fieldname": "hometown_city", "fieldtype": "Data", "width": 150},
        {"label": "Quê quán - Phường/Xã/Đặc khu", "fieldname": "hometown_ward", "fieldtype": "Data", "width": 170},
        {"label": "Nghề nghiệp", "fieldname": "occupation", "fieldtype": "Data", "width": 120},
        {"label": "Nơi ở - Tỉnh/Thành phố", "fieldname": "residence_city", "fieldtype": "Data", "width": 150},
        {"label": "Nơi ở - Phường/Xã/Đặc khu", "fieldname": "residence_ward", "fieldtype": "Data", "width": 170},
        {"label": "Số nhà", "fieldname": "house_no", "fieldtype": "Data", "width": 100},
        {"label": "Địa chỉ đầy đủ", "fieldname": "full_address", "fieldtype": "Data", "width": 220},
    ]

def get_data(filters):
    """
    Hỗ trợ các filter:
      - filters.employee: mã nhân viên (string)
      - filters.employees: danh sách mã nhân viên (list[str])
      - filters.department: phòng ban (string)
      - filters.include_without_relatives: bool -> nếu True, dùng LEFT JOIN để hiện cả NV chưa có nhân thân
    """
    where_clauses = []
    params = []

    # Lọc theo 1 nhân viên
    if filters.get("employee"):
        where_clauses.append("emp.name = %s")
        params.append(filters.get("employee"))

    # Lọc theo danh sách nhân viên
    if filters.get("employees"):
        emp_list = [e for e in filters.get("employees") if e]
        if emp_list:
            # Tạo placeholder (%s, %s, ...) theo độ dài list
            placeholders = ", ".join(["%s"] * len(emp_list))
            where_clauses.append(f"emp.name IN ({placeholders})")
            params.extend(emp_list)

    # Lọc theo phòng ban
    if filters.get("department"):
        where_clauses.append("emp.department = %s")
        params.append(filters.get("department"))

    where_sql = ""
    if where_clauses:
        where_sql = " AND " + " AND ".join(where_clauses)

    # Cho phép chọn hiển thị NV không có nhân thân (LEFT JOIN) hay chỉ có nhân thân (INNER JOIN)
    join_type = "LEFT JOIN" if frappe.utils.cint(filters.get("include_without_relatives")) else "INNER JOIN"

    sql = f"""
        SELECT
            emp.name                        AS employee_code,
            emp.employee_name               AS employee_name,
            rel.name1                       AS relative_name,
            rel.relationship                AS relationship,
            COALESCE(rel.birthday, rel.birth_year) AS dob,
            rel.is_dependent                AS dependent,
            rel.tax_number                  AS tax_code,
            rel.`check`                     AS registered_at_vinatex

        FROM `tabEmployee` emp
        {join_type} `tab{CHILD_TABLE}` rel
            ON rel.parent = emp.name
           AND rel.parenttype = 'Employee'
        WHERE 1=1 {where_sql}
        ORDER BY emp.name, COALESCE(rel.idx, 0)
    """

    rows = frappe.db.sql(sql, params, as_dict=True)

    # Bổ sung placeholder cho các cột chưa có nguồn dữ liệu
    for d in rows:
        d.setdefault("hometown_city", "")
        d.setdefault("hometown_ward", "")
        d.setdefault("occupation", "")
        d.setdefault("residence_city", "")
        d.setdefault("residence_ward", "")
        d.setdefault("house_no", "")
        d.setdefault("full_address", "")

    return rows

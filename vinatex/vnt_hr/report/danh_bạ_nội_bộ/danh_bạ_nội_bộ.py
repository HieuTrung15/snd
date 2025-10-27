# apps/vinatex/vinatex/vnt_hr/report/danh_bạ_nội_bộ/danh_bạ_nội_bộ.py
from __future__ import unicode_literals
from frappe import _
import frappe

def execute(filters=None):
    filters = filters or {}
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data, None

def get_columns(filters=None):
    return [
        # {"label": _("Mã số Nhân sự"), "fieldname": "employee", "fieldtype": "Data", "width": 120},
        {"label": _("Tên Nhân sự"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Chức danh"), "fieldname": "designation", "fieldtype": "Data", "width": 200},
        {"label": _("Phòng/Ban"), "fieldname": "department", "fieldtype": "Data", "width": 180},
        # {"label": _("Công ty"), "fieldname": "company", "fieldtype": "Data", "width": 250},
        {"label": _("Số điện thoại"), "fieldname": "phone", "fieldtype": "Data", "width": 150},
        {"label": _("Email"), "fieldname": "company_email", "fieldtype": "Data", "width": 200},
        {"label": _("Chi nhánh"), "fieldname": "branch", "fieldtype": "Data", "width": 100}
    ]
@frappe.whitelist()
def get_data(filters=None):
    where_sql, params = build_emp_conditions(filters)

    # bổ sung tham số cho CASE + LIKE (đưa % vào giá trị tham số)
    params.update({
        "hdqt": "Hội đồng quản trị%",
        "bks":  "Ban Kiểm soát%",
        "cqdh": "Cơ quan điều hành%",
        "vphdqt": "Văn phòng HĐQT%",
        "bdtvpt": "Ban Đầu tư và Phát triển%",
        "nnl": "Ban Quản lý Nguồn Nhân lực%",
        "tckt": "Ban Tài chính kế toán%",
        "btt": "Ban Truyền thông%",
        "thpc": "Ban Tổng hợp pháp chế%",
        "cntt": "Ban CNTT và Chuyển đổi số%",
        "vptd": "Văn phòng Tập đoàn%",
        "39": "Ban Quản lý Dự án 39-41 VVK%",
        "vcc": "Ban Quản lý Dự án Vải chống cháy%",
        "tcdq": "Ban Tổ chức Đảng ủy%",
        "tqdu": "Ban Tuyên giáo Đảng ủy%",
        "ubkt": "Cơ quan Ủy ban Kiểm tra Đảng ủy%",
        "vpdu": "Văn phòng Đảng ủy%",
        "cddm": "Công đoàn Dệt May Việt Nam%",
        "lx": "Vinateximex + Lái xe kiêm nhiệm%",
        "cg": "Chuyên gia%"
    })

    sql = """
        SELECT
            emp.name            AS employee,
            emp.employee_name   AS employee_name,
            emp.designation     AS designation,
            emp.company         AS company,
            emp.branch          AS branch,
            emp.cell_number     AS phone,
            emp.company_email   AS company_email,
            dept.department_name AS department
        FROM `tabEmployee` emp
        LEFT JOIN `tabDepartment` dept ON emp.department = dept.name
        WHERE emp.status != 'Left'
    """ + where_sql + """
        ORDER BY CASE
            WHEN emp.department LIKE %(hdqt)s THEN 1
            WHEN emp.department LIKE %(bks)s  THEN 2
            WHEN emp.department LIKE %(cqdh)s  THEN 3
            WHEN emp.department LIKE %(vphdqt)s  THEN 4
            WHEN emp.department LIKE %(bdtvpt)s  THEN 5
            WHEN emp.department LIKE %(nnl)s  THEN 6
            WHEN emp.department LIKE %(tckt)s  THEN 7
            WHEN emp.department LIKE %(btt)s  THEN 8
            WHEN emp.department LIKE %(thpc)s  THEN 9
            WHEN emp.department LIKE %(cntt)s  THEN 10
            WHEN emp.department LIKE %(vptd)s  THEN 11
            WHEN emp.department LIKE %(39)s  THEN 12
            WHEN emp.department LIKE %(vcc)s  THEN 13
            WHEN emp.department LIKE %(tcdq)s  THEN 14
            WHEN emp.department LIKE %(tqdu)s  THEN 15
            WHEN emp.department LIKE %(vpdu)s  THEN 16
            WHEN emp.department LIKE %(cddm)s  THEN 17
            WHEN emp.department LIKE %(lx)s  THEN 18
            WHEN emp.department LIKE %(cg)s  THEN 19
            ELSE 999
        END,
        emp.employee_name
    """

    return frappe.db.sql(sql, params, as_dict=True)



def build_emp_conditions(filters=None):
    conds = []
    params = {}

    if filters.get("employee"):
        conds.append("AND emp.name = %(employee)s")   
        params["employee"] = filters["employee"]

    if filters.get("company"):
        conds.append("AND emp.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("department"):
        conds.append("AND emp.department = %(department)s")
        params["department"] = filters["department"]

    where_sql = " ".join(conds)
    return where_sql, params

def build_cpn_conditions(filters):
    conds = []
    params = {}

    if filters.get("company"):
        conds.append("cpn.name = %(company)s")
        params["company"] = filters["company"]

    where_sql = f"WHERE {' AND '.join(conds)}" if conds else ""
    return where_sql, params

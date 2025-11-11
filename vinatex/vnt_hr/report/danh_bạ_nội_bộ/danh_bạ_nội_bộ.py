from __future__ import unicode_literals
from frappe import _
import frappe
import json

def execute(filters=None):
    filters = normalize_filters(filters)
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data, None

def get_columns(filters=None):
    return [
        {"label": _("Tên Nhân sự"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Chức danh"), "fieldname": "designation", "fieldtype": "Data", "width": 200},
        {"label": _("Phòng/Ban"), "fieldname": "department", "fieldtype": "Data", "width": 180},
        {"label": _("Số điện thoại"), "fieldname": "phone", "fieldtype": "Data", "width": 150},
        {"label": _("Email"), "fieldname": "company_email", "fieldtype": "Data", "width": 200},
        {"label": _("Chi nhánh"), "fieldname": "branch", "fieldtype": "Data", "width": 100}
    ]

def normalize_filters(filters):
    """Đảm bảo filters luôn là dict (hỗ trợ cả string JSON từ JS)."""
    if filters is None:
        return {}
    if isinstance(filters, dict):
        return filters
    if isinstance(filters, str):
        txt = filters.strip()
        if not txt:
            return {}
        try:
            return json.loads(txt)
        except Exception:
            return {}
    return {}

@frappe.whitelist()
def get_filter_options():
    """
    Trả về list Chi nhánh và list Phòng/Ban để fill vào <select>.
    """
    branches = frappe.db.sql(
        """
        SELECT DISTINCT emp.branch AS branch
        FROM `tabEmployee` emp
        WHERE emp.status != 'Left' AND IFNULL(emp.branch,'')!=''
        ORDER BY emp.branch
        """,
        as_dict=True,
    )

    departments = frappe.db.sql(
        """
        SELECT DISTINCT dept.department_name AS department
        FROM `tabDepartment` dept
        WHERE dept.disabled = 0 AND IFNULL(dept.department_name,'')!=''
        ORDER BY dept.department_name
        """,
        as_dict=True,
    )

    return {
        "branches": [b["branch"] for b in branches if b.get("branch")],
        "departments": [d["department"] for d in departments if d.get("department")],
    }

@frappe.whitelist()
def get_data(filters=None):
    filters = normalize_filters(filters)

    special_role = filters.get("special_role")

    # Build WHERE + params
    where_sql, params = build_emp_conditions(filters)

    # tham số phục vụ ORDER BY CASE
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

    # join child table của Company
    rep_join_sql = ""
    rep_where_sql = ""
    if special_role in ["nguoi_dai_dien", "ke_toan_truong"]:
        rep_join_sql = """
            INNER JOIN `tabVNT Company Representative` rep
                ON rep.employee = emp.name
        """

        if special_role == "nguoi_dai_dien":
            # CT HĐQT, TV HĐQT, TGĐ, TV BKS
            rep_where_sql = """
                AND rep.position IN ('CT HĐQT', 'TV HĐQT', 'TGĐ', 'TV BKS')
            """
        elif special_role == "ke_toan_truong":
            # Kế toán trưởng
            rep_where_sql = """
                AND rep.position IN ('Kế toán trưởng')
            """

    sql = f"""
        SELECT DISTINCT
            emp.name              AS employee,
            emp.employee_name     AS employee_name,
            emp.designation       AS designation,
            emp.company           AS company,
            emp.branch            AS branch,
            emp.cell_number       AS phone,
            emp.company_email     AS company_email,
            dept.department_name  AS department
        FROM `tabEmployee` emp
        LEFT JOIN `tabDepartment` dept
            ON emp.department = dept.name
        {rep_join_sql}
        WHERE emp.status != 'Left'
        {where_sql}
        {rep_where_sql}
        ORDER BY CASE
            WHEN emp.designation LIKE 'Chủ tịch Hội đồng quản trị Tập đoàn' THEN -10
            WHEN emp.designation LIKE 'Tổng Giám đốc Tập đoàn' THEN -9
            WHEN emp.designation LIKE 'Phó Tổng Giám đốc Tập đoàn' THEN -8
            WHEN emp.designation LIKE 'Kế toán trưởng Tập đoàn' THEN -6

            WHEN emp.department LIKE %(hdqt)s   THEN 1
            WHEN emp.department LIKE %(bks)s    THEN 2
            WHEN emp.department LIKE %(cqdh)s   THEN 3
            WHEN emp.department LIKE %(vphdqt)s THEN 4
            WHEN emp.department LIKE %(bdtvpt)s THEN 5
            WHEN emp.department LIKE %(nnl)s    THEN 6
            WHEN emp.department LIKE %(tckt)s   THEN 7
            WHEN emp.department LIKE %(btt)s    THEN 8
            WHEN emp.department LIKE %(thpc)s   THEN 9
            WHEN emp.department LIKE %(cntt)s   THEN 10
            WHEN emp.department LIKE %(vptd)s   THEN 11
            WHEN emp.department LIKE %(39)s     THEN 12
            WHEN emp.department LIKE %(vcc)s    THEN 13
            WHEN emp.department LIKE %(tcdq)s   THEN 14
            WHEN emp.department LIKE %(tqdu)s   THEN 15
            WHEN emp.department LIKE %(vpdu)s   THEN 16
            WHEN emp.department LIKE %(cddm)s   THEN 17
            WHEN emp.department LIKE %(lx)s     THEN 18
            WHEN emp.department LIKE %(cg)s     THEN 19

            ELSE 999
        END,
        emp.employee_name
    """

    return frappe.db.sql(sql, params, as_dict=True)



def build_emp_conditions(filters=None):
    filters = normalize_filters(filters)

    conds = []
    params = {}

    # chỉ lấy employee cụ thể (tùy chọn)
    if filters.get("employee"):
        conds.append("emp.name = %(employee)s")
        params["employee"] = filters["employee"]

    # lọc theo công ty
    if filters.get("company"):
        conds.append("emp.company = %(company)s")
        params["company"] = filters["company"]

    # lọc theo chi nhánh
    if filters.get("branch"):
        conds.append("emp.branch = %(branch)s")
        params["branch"] = filters["branch"]

    # lọc theo phòng ban cụ thể (theo tên hiển thị department_name)
    if filters.get("department"):
        conds.append("dept.department_name = %(department)s")
        params["department"] = filters["department"]

    # build WHERE ... AND ...
    where_sql = ""
    if conds:
        where_sql = "AND " + " AND ".join(conds)

    return where_sql, params

@frappe.whitelist()
def get_company_representatives(company=None, rep_type=None, custom_industry=None):
    """
    Trả thông tin đại diện / kế toán trưởng theo Company.

    Params:
        company         (str, optional)
        rep_type        (str, optional): "NDD" / "KTT"
        custom_industry (str, optional): lọc theo Company.custom_industry
    """

    conds = []
    params = {}

    if company:
        conds.append("(c.name = %(company)s OR c.company_name = %(company)s)")
        params["company"] = company

    if rep_type in ("NDD", "KTT"):
        conds.append("rep.type = %(rep_type)s")
        params["rep_type"] = rep_type
    else:
        conds.append("rep.type IN ('NDD','KTT')")

    # NEW: lọc theo custom_industry
    if custom_industry:
        conds.append("c.custom_industry = %(custom_industry)s")
        params["custom_industry"] = custom_industry

    where_sql = ""
    if conds:
        where_sql = "WHERE " + " AND ".join(conds)

    sql = f"""
        SELECT DISTINCT
            c.company_name            AS company_name,
            rep.type                  AS representative_type,
            rep.position              AS position,
            COALESCE(emp.employee_name, rep.employee) AS employee_name,
            rep.email                 AS email,
            rep.phone                 AS phone
        FROM `tabCompany` c
        INNER JOIN `tabVNT Company Representative` rep
            ON rep.parent = c.name
        LEFT JOIN `tabEmployee` emp
            ON emp.name = rep.employee
        {where_sql}
        ORDER BY
            c.company_name ASC,
            FIELD(rep.type, 'NDD','KTT'),
            rep.position ASC
    """

    rows = frappe.db.sql(sql, params, as_dict=True)
    return rows



def build_cpn_conditions(filters=None):
    filters = normalize_filters(filters)

    conds = []
    params = {}

    if filters.get("company"):
        conds.append("cpn.name = %(company)s")
        params["company"] = filters["company"]

    where_sql = f"WHERE {' AND '.join(conds)}" if conds else ""
    return where_sql, params

@frappe.whitelist()
def get_company_industries():
    """
    Trả về danh sách distinct Company.custom_industry
    để fill vào <select> lọc ở tab Người đại diện.
    """
    rows = frappe.db.sql(
        """
        SELECT DISTINCT custom_industry
        FROM `tabCompany`
        WHERE IFNULL(custom_industry, '') != ''
        ORDER BY custom_industry
        """,
        as_dict=True,
    )
    return [r.custom_industry for r in rows if r.get("custom_industry")]


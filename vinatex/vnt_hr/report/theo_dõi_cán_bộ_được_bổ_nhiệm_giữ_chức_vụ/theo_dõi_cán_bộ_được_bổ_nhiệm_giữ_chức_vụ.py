import frappe

DECISION_TYPES = ("Quyết định bổ nhiệm", "Quyết định điều động và bổ nhiệm")

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(data)
    return columns, data, None, None, summary


def get_columns():
    return [
        # {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Data", "options": "Employee", "width": 110},
        {"label": "Họ và tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Chức danh (sau QĐ)", "fieldname": "designation", "fieldtype": "Data", "width": 180},
        {"label": "Công ty (NV)", "fieldname": "employee_company", "fieldtype": "Data", "options": "Company", "width": 160},
        {"label": "Phòng ban (NV)", "fieldname": "employee_department", "fieldtype": "Data", "options": "Department", "width": 160},
        {"label": "Loại quyết định", "fieldname": "decision_type", "fieldtype": "Data", "width": 200},
        {"label": "Số quyết định", "fieldname": "decision_number", "fieldtype": "Data", "width": 140},
        {"label": "Ngày quyết định", "fieldname": "decision_date", "fieldtype": "Date", "width": 120},
        {"label": "Công ty (QĐ)", "fieldname": "decision_company", "fieldtype": "Data", "options": "Company", "width": 160},
        {"label": "Phòng ban (QĐ)", "fieldname": "decision_department", "fieldtype": "Data", "options": "Department", "width": 160},
        {"label": "Người ký", "fieldname": "signer_name", "fieldtype": "Data", "width": 160},
        {"label": "Nội dung QĐ", "fieldname": "decision_content", "fieldtype": "Data", "width": 250},
        {"label": "Mã QĐ", "fieldname": "decision_id", "fieldtype": "Data", "width": 120},
    ]


def get_data(filters):
    # docstatus
    docstatus = None
    ds_text = (filters.get("docstatus") or "1(Submitted)").strip()
    if ds_text.startswith("0"):
        docstatus = 0
    elif ds_text.startswith("1"):
        docstatus = 1
    elif ds_text.startswith("2"):
        docstatus = 2

    conds = [
        "d.decision_type IN %(decision_types)s",
        "di.parent = d.name",
        "di.parenttype = 'VNT Decision'"
    ]
    params = {"decision_types": DECISION_TYPES}

    if docstatus is not None:
        conds.append("d.docstatus = %(docstatus)s")
        params["docstatus"] = docstatus

    if filters.get("company"):
        conds.append("COALESCE(di.cur_company, di.company) = %(company)s")
        params["company"] = filters.company

    if filters.get("department"):
        conds.append("COALESCE(di.cur_department, di.department) = %(department)s")
        params["department"] = filters.department

    if filters.get("from_date"):
        conds.append("d.date >= %(from_date)s")
        params["from_date"] = filters.from_date

    if filters.get("to_date"):
        conds.append("d.date <= %(to_date)s")
        params["to_date"] = filters.to_date

    where = " AND ".join(conds)

    # chọn query: chỉ 1 dòng mới nhất / hay tất cả
    if int(filters.get("only_latest_per_employee") or 0):
        # dùng window function nếu DB hỗ trợ (MariaDB 10.6+)
        sql = f"""
            SELECT * FROM (
              SELECT
                d.name AS decision_id,
                d.date AS decision_date,
                d.decision_type,
                d.decision_number,
                d.company AS decision_company,
                d.department AS decision_department,
                d.signer, d.signer_name,
                d.decision_content,
                di.employee, di.employee_name,
                COALESCE(di.cur_designation, di.designation, d.desination) AS designation,
                COALESCE(di.cur_company, di.company)                        AS employee_company,
                COALESCE(di.cur_department, di.department)                  AS employee_department,
                ROW_NUMBER() OVER (
                  PARTITION BY di.employee
                  ORDER BY d.date DESC, d.modified DESC, d.name DESC
                ) AS rn
              FROM `tabVNT Decision` d
              JOIN `tabVNT Decision Item` di
                ON di.parent = d.name AND di.parenttype = 'VNT Decision'
              WHERE {where}
            ) x
            WHERE x.rn = 1
            ORDER BY x.decision_date DESC, x.employee
        """
        return frappe.db.sql(sql, params, as_dict=True)

    # lấy tất cả
    sql = f"""
        SELECT
          d.name AS decision_id,
          d.date AS decision_date,
          d.decision_type,
          d.decision_number,
          d.company AS decision_company,
          d.department AS decision_department,
          d.signer, d.signer_name,
          d.decision_content,
          di.employee, di.employee_name,
          COALESCE(di.cur_designation, di.designation, d.desination) AS designation,
          COALESCE(di.cur_company, di.company)                        AS employee_company,
          COALESCE(di.cur_department, di.department)                  AS employee_department
        FROM `tabVNT Decision` d
        JOIN `tabVNT Decision Item` di
          ON di.parent = d.name AND di.parenttype = 'VNT Decision'
        WHERE {where}
        ORDER BY d.date DESC, d.modified DESC, d.name DESC, di.employee
    """
    return frappe.db.sql(sql, params, as_dict=True)


def get_summary(rows):
    total = len(rows)
    appoint = sum(1 for r in rows if r.get("decision_type") == "Quyết định bổ nhiệm")
    appoint_move = sum(1 for r in rows if r.get("decision_type") == "Quyết định điều động và bổ nhiệm")
    return [
        {"label": "Tổng nhân sự", "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": "Bổ nhiệm", "value": appoint, "indicator": "Green", "datatype": "Int"},
        {"label": "Điều động & Bổ nhiệm", "value": appoint_move, "indicator": "Green", "datatype": "Int"},
    ]

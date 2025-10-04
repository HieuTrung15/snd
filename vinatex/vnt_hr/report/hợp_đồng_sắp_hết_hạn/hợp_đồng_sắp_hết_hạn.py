import frappe
from frappe.utils import getdate, add_days, today

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 220},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "width": 220},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Data", "width": 180},
        {"label": "Loại hợp đồng", "fieldname": "type", "fieldtype": "Data", "width": 120},
        {"label": "Thời hạn HĐ", "fieldname": "contract_term", "fieldtype": "Data", "width": 120},
        {"label": "Ngày hiệu lực HĐ", "fieldname": "from_date", "fieldtype": "Date", "width": 150},
        {"label": "Ngày hết hạn HĐ", "fieldname": "contract_end_date", "fieldtype": "Date", "width": 150},
        {"label": "Còn (ngày)", "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 100},
        {"label": "Email", "fieldname": "email", "fieldtype": "Data", "width": 180},
        {"label": "SĐT", "fieldname": "phone", "fieldtype": "Data", "width": 120}
    ]

def get_data(filters):
    start_date = getdate(filters.get("from_date") or today())
    end_date   = getdate(filters.get("to_date") or add_days(today(), 30))
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    include_expired = filters.get("include_expired_before_from_date", 1)  # 1 = có gộp HĐ đã hết hạn trước from_date

    base_params = {
        "start": start_date,
        "end": end_date,
        "status": "Active",
        "today": getdate(today()),
    }
    where_common = [
        "c.validity = 1",
        "c.to_date IS NOT NULL",
        "e.status = %(status)s",
    ]
    if filters.get("employee"):
        where_common.append("e.name = %(employee)s")
        base_params["employee"] = filters["employee"]
    if filters.get("department"):
        where_common.append("e.department = %(department)s")
        base_params["department"] = filters["department"]

    where_common_sql = " AND ".join(where_common)

    # 1) Trong khoảng from_date..to_date
    sql_in_window = f"""
        SELECT
            e.name as employee,
            e.employee_name,
            e.department,
            e.designation,
            c.type as type,
            c.contract_term as contract_term,
            c.from_date as from_date,
            c.to_date as contract_end_date,
            DATEDIFF(c.to_date, %(today)s) as days_to_expiry,
            e.company_email as email,
            e.cell_number as phone
        FROM `tabVNT Contract` c
        JOIN `tabEmployee` e ON e.name = c.parent
        WHERE {where_common_sql}
          AND c.to_date BETWEEN %(start)s AND %(end)s
    """

    # 2) Hết hạn trước from_date nhưng validity=1 (overdue)
    sql_expired = f"""
        SELECT
            e.name as employee,
            e.employee_name,
            e.department,
            e.designation,
            c.type as type,
            c.contract_term as contract_term,
            c.from_date as from_date,
            c.to_date as contract_end_date,           
            DATEDIFF(c.to_date, %(today)s) as days_to_expiry,
            e.company_email as email,
            e.cell_number as phone
        FROM `tabVNT Contract` c
        JOIN `tabEmployee` e ON e.name = c.parent
        WHERE {where_common_sql}
          AND c.to_date < %(start)s
    """

    if int(include_expired):
        sql = f"""
            ({sql_in_window})
            UNION ALL
            ({sql_expired})
            ORDER BY contract_end_date ASC, employee ASC
        """
        return frappe.db.sql(sql, base_params, as_dict=True)
    else:
        sql = f"""
            {sql_in_window}
            ORDER BY contract_end_date ASC, employee ASC
        """
        return frappe.db.sql(sql, base_params, as_dict=True)


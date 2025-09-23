import frappe

def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Mã nhân viên",  "fieldname": "employee",      "fieldtype": "Data", "width": 110},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Phòng ban",     "fieldname": "department",    "fieldtype": "Data", "width": 160},
        {"label": "Công ty",       "fieldname": "company",       "fieldtype": "Data", "width": 160},
        {"label": "Ngày đi",       "fieldname": "from_date",     "fieldtype": "Date", "width": 110},
        {"label": "Ngày về",       "fieldname": "to_date",       "fieldtype": "Date", "width": 110},
        {"label": "Địa điểm đến",  "fieldname": "destination",   "fieldtype": "Data", "width": 200},
    ]

    conditions = []
    values = {}

    if filters.get("employee"):
        conditions.append("emp.name = %(employee)s")
        values["employee"] = filters["employee"]

    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        values["department"] = filters["department"]

    if filters.get("company"):
        conditions.append("emp.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("from_date"):
        conditions.append("la.from_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("la.to_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("leave_type"):
        conditions.append("la.leave_type = %(leave_type)s")
        values["leave_type"] = filters["leave_type"]

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    data = frappe.db.sql(f"""
        SELECT
            item.employee        AS employee,
            la.employee_name   AS employee_name,
            emp.department     AS department,
            emp.company        AS company,
            la.from_date       AS from_date,
            la.to_date         AS to_date,
            la.description     AS destination
        FROM `tabLeave Application` la
        LEFT JOIN `tabVNT Business Trip Request Items` item ON la.name = item.parent
        LEFT JOIN `tabEmployee` emp ON emp.name = la.employee
        LEFT JOIN `tabVNT Business Trip Request Transportation` tran ON la.name = tran.parent
        
        {where_sql}
        ORDER BY la.from_date ASC, la.employee_name ASC
    """, values, as_dict=True)

    return columns, data

import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {"label": "Họ và tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Giới tính", "fieldname": "gender", "fieldtype": "Data", "width": 100},
        {"label": "Ngày sinh", "fieldname": "date_of_birth", "fieldtype": "Date", "width": 120},
        {"label": "Chức vụ hiện nay", "fieldname": "designation", "fieldtype": "Data", "width": 250},
        {"label": "Nhiệm kỳ bổ nhiệm", "fieldname": "from_date", "fieldtype": "Date", "width": 200},
        {"label": "Ngày đến hạn bổ nhiệm lại", "fieldname": "to_date", "fieldtype": "Date", "width": 200},
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date") and filters.get("to_date"):
        conditions.append("iwh.from_date BETWEEN %(from_date)s AND %(to_date)s")
        values["from_date"] = filters.get("from_date")
        values["to_date"] = filters.get("to_date")

    sql_query = f"""
        SELECT 
            e.employee_name,
            e.gender,
            e.date_of_birth,
            CONCAT(iwh.designation, ' - ', iwh.department) AS designation,
            iwh.from_date,
            iwh.to_date
        FROM `tabEmployee Internal Work History` iwh
        JOIN `tabEmployee` e ON e.name = iwh.parent
        { "WHERE " + " AND ".join(conditions) if conditions else "" }
        ORDER BY iwh.from_date DESC
    """

    results = frappe.db.sql(sql_query, values, as_dict=True)

    return results

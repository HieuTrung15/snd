import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": "Chức danh viết tắt", "fieldname": "designation", "fieldtype": "Data", "width": 120},
        {"label": "Số lượng nhân viên", "fieldname": "employee_count", "fieldtype": "Int", "width": 120},
        {"label": "Độ tuổi TB", "fieldname": "avg_age", "fieldtype": "Float", "width": 120},
        {"label": "Tên đầy đủ", "fieldname": "designation_full", "fieldtype": "Data", "width": 250},
    ]

    data = get_data(filters)
    return columns, data


def get_data(filters=None):
    """Truy vấn dữ liệu chung cho report và chart"""
    conditions = []
    values = {}

    if filters.get("designation"):
        conditions.append("emp.designation = %(designation)s")
        values["designation"] = filters.get("designation")

    if filters.get("company"):
        conditions.append("emp.company = %(company)s")
        values["company"] = filters.get("company")

    condition_sql = ""
    if conditions:
        condition_sql = " AND " + " AND ".join(conditions)

    query = f"""
        SELECT 
            emp.designation,
            COUNT(emp.name) as employee_count,
            AVG(TIMESTAMPDIFF(YEAR, emp.date_of_birth, CURDATE())) as avg_age,
            des.designation_name as designation_full
        FROM `tabEmployee` emp
        LEFT JOIN `tabDesignation` des ON emp.designation = des.name
        WHERE emp.status = 'Active' {condition_sql}
        GROUP BY emp.designation, des.designation_name
    """

    return frappe.db.sql(query, values, as_dict=True)


@frappe.whitelist()
def get_chart_data(filters=None):
    """API cho Dashboard Chart"""
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)

    data = get_data(filters)

    abbrs = [row["designation"] for row in data]
    full_labels = [row["designation_full"] or "Khác" for row in data]
    counts = [row["employee_count"] for row in data]
    avg_ages = [row["avg_age"] or 0 for row in data]

    return {
        "labels": abbrs,  # dùng abbr cho trục X
        "datasets": [
            {
                "name": "Số lượng nhân viên",
                "values": counts,
                "chartType": "bar"
            },
            {
                "name": "Độ tuổi TB",
                "values": avg_ages,
                "chartType": "line"
            }
        ],
        "custom_tooltips": full_labels
    }

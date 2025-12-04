import frappe

def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": "Công ty",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 250,
        },
        {
            "label": "Kho",
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 250,
        },
        {
            "label": "Số lượng thực tế",
            "fieldname": "actual_qty",
            "fieldtype": "Float",
            "width": 150,
        },
        {
            "label": "Giá trị tồn kho",
            "fieldname": "stock_value",
            "fieldtype": "Float",
            "width": 180,
        }
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters.get("company"):
        conditions.append("w.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("warehouse"):
        conditions.append("b.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]

    condition_sql = ""
    if conditions:
        condition_sql = "AND " + " AND ".join(conditions)

    query = f"""
        SELECT
            w.company,
            b.warehouse,
            SUM(b.actual_qty) AS actual_qty,
            SUM(b.stock_value) AS stock_value
        FROM `tabBin` b
        JOIN `tabWarehouse` w ON w.name = b.warehouse
        WHERE 1 = 1
            {condition_sql}
        GROUP BY w.company, b.warehouse
        ORDER BY b.stock_value DESC, w.company, b.warehouse
    """

    return frappe.db.sql(query, values, as_dict=True)

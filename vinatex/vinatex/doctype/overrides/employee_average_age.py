import frappe

@frappe.whitelist()
def get_average_age(filters=None):
    val = frappe.db.sql("""
        SELECT FLOOR(AVG(TIMESTAMPDIFF(YEAR, date_of_birth, CURDATE())))
        FROM `tabEmployee`
        WHERE status = 'Active'
    """)
    return int(val[0][0]) if val and val[0][0] is not None else 0

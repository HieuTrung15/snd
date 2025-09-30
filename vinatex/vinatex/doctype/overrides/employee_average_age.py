import frappe

@frappe.whitelist()
def get_average_age(filters=None):
    # filters có thể được Number Card truyền vào, cứ để tham số cho an toàn
    val = frappe.db.sql("""
        SELECT ROUND(AVG(TIMESTAMPDIFF(YEAR, date_of_birth, CURDATE())), 1)
        FROM `tabEmployee`
        WHERE status = 'Active'
    """)
    return float(val[0][0]) if val and val[0][0] is not None else 0.0

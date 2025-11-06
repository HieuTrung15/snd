import frappe


def salary_slip_permission_query_conditions(user):
    """Restrict VNT Salary Slip list to the employee linked to the user."""
    if not user or user == "Guest":
        return "1=0"
    if user == "Administrator":
        return ""

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return "1=0"

    return f"`tabVNT Salary Slip`.`employee` = {frappe.db.escape(employee)}"


def salary_slip_has_permission(doc, user):
    """Block direct access to salary slips not belonging to the user's employee."""
    if not user or user == "Guest":
        return False
    if user == "Administrator":
        return True

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    return bool(employee and doc.employee == employee)

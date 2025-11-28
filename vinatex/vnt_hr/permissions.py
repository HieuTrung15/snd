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


def get_permission_query_conditions(user):
    if not user:
        user = frappe.session.user

    # Cho Administrator hoặc System Manager thấy hết
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    # Nhân viên chỉ thấy ToDo:
    # - do chính họ tạo (owner)
    # - hoặc giao cho họ (allocated_to)
    return f"""
        (`tabToDo`.owner = '{user}'
         OR `tabToDo`.allocated_to = '{user}')
    """

def vnt_monthly_payroll_per(user):
    if not user or user == "Guest":
        return "1=0"

    if user == "Administrator":
        return ""

    hr_salary_users = {"tult@vinatex.com.vn", "hoaltm@vinatex.com.vn", "thaottt@vinatex.com.vn"}
    if user in hr_salary_users:
        return ""

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return "1=0"

    return f"`tabVNT Monthly Payroll`.`employee` = '{employee}'"


def vnt_monthly_payroll_has_permission(doc, user):
    frappe.throw("abcs")
    if not user or user == "Guest":
        return False

    if user == "Administrator":
        return True

    hr_salary_users = {"tult@vinatex.com.vn", "hoaltm@vinatex.com.vn", "thaottt@vinatex.com.vn"}
    if user in hr_salary_users:
        return True

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return False

    return doc.employee == employee

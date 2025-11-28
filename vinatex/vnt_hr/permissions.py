import frappe

HR_SALARY_USERS = {
    "tult@vinatex.com.vn",
    "hoaltm@vinatex.com.vn",
    "thaottt@vinatex.com.vn",
}


def is_hr_salary_user(user: str | None) -> bool:
    """Return True if user is in HR salary list or Administrator."""
    if not user or user == "Guest":
        return False
    if user == "Administrator":
        return True
    return user in HR_SALARY_USERS


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
    # Không có user hoặc Guest -> không thấy gì
    if not user or user == "Guest":
        return "1=0"

    # Admin -> thấy hết
    if is_hr_salary_user(user):
        return ""

    # Các user khác -> không được thấy gì
    return "1=0"

def vnt_monthly_payroll_has_permission(doc, user):
    # Guest/out -> chặn
    if not user or user == "Guest":
        return False

    # Admin -> cho
    if is_hr_salary_user(user):
        return True

    # Còn lại -> cấm hết, kể cả phiếu của chính mình
    return False


def vnt_13th_month_salary_has_permission(doc=None, user=None, ptype=None):
    """
    Chỉ cho phép HR lương hoặc Administrator truy cập (mọi perm).
    """
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    if is_hr_salary_user(user):
        return True
    return False

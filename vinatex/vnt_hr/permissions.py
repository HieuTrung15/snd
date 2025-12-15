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


# === VNT Document Management ===
def _user_employee(user: str | None) -> str | None:
    if not user or user == "Guest":
        return None
    # Ưu tiên khớp đúng, nếu không thử khớp không phân biệt hoa/thường
    emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if emp:
        return emp
    try:
        emp = frappe.db.sql(
            "select name from `tabEmployee` where lower(user_id)=lower(%s) limit 1",
            user,
        )
        return emp[0][0] if emp else None
    except Exception:
        return None


def vnt_document_management_permission_query_conditions(user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return "1=0"

    allow_empty_type = "ifnull(`tabVNT Document Management`.type, '') = ''"

    # Cho Administrator/System Manager view all
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    emp = _user_employee(user)
    if not emp:
        return allow_empty_type

    esc = frappe.db.escape(emp)
    return f"""
        (
            {allow_empty_type}
            OR `tabVNT Document Management`.employee = {esc}
            OR `tabVNT Document Management`.handler = {esc}
            OR `tabVNT Document Management`.nguoi_chu_tri = {esc}
            OR `tabVNT Document Management`.cv_xu_ly = {esc}
            OR EXISTS (
                SELECT 1 FROM `tabVNT Document Management Item2` child
                WHERE child.parent = `tabVNT Document Management`.name
                  AND child.parenttype = 'VNT Document Management'
                  AND child.employee = {esc}
                  AND (child.chu_tri = 1 OR child.phoi_hop = 1)
            )
            OR EXISTS (
                SELECT 1 FROM `tabVNT Document Management Item` it
                WHERE it.parent = `tabVNT Document Management`.name
                  AND it.parenttype = 'VNT Document Management'
                  AND (
                    it.nguoi_phoi_hop = {esc}
                    OR it.cv_xu_ly = {esc}
                  )
            )
        )
    """


def vnt_document_management_has_permission(doc=None, user=None, ptype=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True

    # Khi doc=None (check cấp doctype), cho phép để còn áp dụng query_conditions
    if not doc:
        return True

    # Văn bản chưa chọn loại -> mở cho tất cả
    if not (getattr(doc, "type", None) or "").strip():
        return True

    emp = _user_employee(user)
    if not emp:
        return False

    # 1) Kiểm tra document đã load
    direct = {
        doc.employee,
        getattr(doc, "handler", None),
        getattr(doc, "nguoi_chu_tri", None),
        getattr(doc, "cv_xu_ly", None),
    }
    if emp in direct:
        return True

    # 2) Kiểm tra child đã load
    for row in getattr(doc, "items", []) or []:
        if getattr(row, "employee", None) != emp:
            continue
        if getattr(row, "chu_tri", 0) or getattr(row, "phoi_hop", 0):
            return True

    for row in getattr(doc, "items2", []) or []:
        if getattr(row, "nguoi_phoi_hop", None) == emp:
            return True
        if getattr(row, "cv_xu_ly", None) == emp:
            return True

    # 3) Fallback truy vấn khi doc chưa load child
    if frappe.db.exists(
        "VNT Document Management Item2",
        {"parent": doc.name, "parenttype": doc.doctype, "employee": emp, "chu_tri": 1},
    ):
        return True
    if frappe.db.exists(
        "VNT Document Management Item2",
        {"parent": doc.name, "parenttype": doc.doctype, "employee": emp, "phoi_hop": 1},
    ):
        return True
    if frappe.db.exists(
        "VNT Document Management Item",
        {"parent": doc.name, "parenttype": doc.doctype, "nguoi_phoi_hop": emp},
    ):
        return True
    return bool(
        frappe.db.exists(
            "VNT Document Management Item",
            {"parent": doc.name, "parenttype": doc.doctype, "cv_xu_ly": emp},
        )
    )

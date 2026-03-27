import frappe

HR_SALARY_USERS = {
    "tult@vinatex.com.vn",
    "thudtx@vinatex.com.vn",
    "thaottt@vinatex.com.vn",
}

VNT_NEW_FEED_EDITOR_ROLES = {
    "System Manager",
    "VNT New Feed",
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


def vnt_new_feed_has_permission(doc=None, user=None, ptype=None):
    """Keep VNT New Feed read-only except for explicit editor cases."""
    user = user or frappe.session.user

    if not user or user == "Guest":
        return False

    if ptype not in {"create", "write", "delete", "submit", "cancel", "amend"}:
        return None

    is_role_editor = user == "Administrator" or bool(
        VNT_NEW_FEED_EDITOR_ROLES.intersection(frappe.get_roles(user))
    )
    if is_role_editor:
        return True

    # Non-editor users only get write on records they created
    # or when they are the employee selected in "Người lập phiếu".
    if ptype == "write" and doc:
        owner = (getattr(doc, "owner", None) or "").strip().lower()
        if owner == user.lower():
            return True

        selected_employee = (getattr(doc, "employee", None) or "").strip()
        if selected_employee:
            user_employee = _user_employee(user)
            if user_employee and user_employee == selected_employee:
                return True

            # Fallback when the field stores user id style value.
            if selected_employee.lower() == user.lower():
                return True

    # Other users remain read-only.
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


def _is_tap_doan_leader(user: str | None) -> bool:
    if not user or user == "Guest":
        return False
    roles = {(r or "").strip().lower() for r in frappe.get_roles(user)}
    return "lãnh đạo tập đoàn" in roles or "lanh dao tap doan" in roles


def vnt_document_management_permission_query_conditions(user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return "1=0"

    allow_empty_type = "ifnull(`tabVNT Document Management`.vnt_type, '') = ''"

    # Cho Administrator/System Manager/Lãnh đạo tập đoàn view all
    if user == "Administrator" or "System Manager" in frappe.get_roles(user) or _is_tap_doan_leader(user):
        return ""

    emp = _user_employee(user)
    if not emp:
        return allow_empty_type

    emp_dept = frappe.db.get_value("Employee", emp, "department")
    esc = frappe.db.escape(emp)
    esc_dept = frappe.db.escape(emp_dept) if emp_dept else None
    outgoing_clause = ""
    if esc_dept:
        outgoing_clause = f"""
            OR (
                `tabVNT Document Management`.vnt_type = 'Công văn đi'
                AND (
                    `tabVNT Document Management`.employee = {esc}
                    OR `tabVNT Document Management`.nguoi_ky = {esc}
                    OR `tabVNT Document Management`.department = {esc_dept}
                )
            )
        """
    else:
        outgoing_clause = f"""
            OR (
                `tabVNT Document Management`.vnt_type = 'Công văn đi'
                AND (
                    `tabVNT Document Management`.employee = {esc}
                    OR `tabVNT Document Management`.nguoi_ky = {esc}
                )
            )
        """

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
            OR EXISTS (
                SELECT 1 FROM `tabVNT Document Management Item6` i6
                WHERE i6.parent = `tabVNT Document Management`.name
                  AND i6.parenttype = 'VNT Document Management'
                  AND i6.parentfield IN ('items6', 'items7')
                  AND i6.employee = {esc}
            )
            {outgoing_clause}
        )
    """


def vnt_document_management_has_permission(doc=None, user=None, ptype=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    if user == "Administrator" or "System Manager" in frappe.get_roles(user) or _is_tap_doan_leader(user):
        return True

    # Khi doc=None (check cấp doctype), cho phép để còn áp dụng query_conditions
    if not doc:
        return True

    doc_type = (
        getattr(doc, "vnt_type", None)
        or getattr(doc, "type", None)
        or ""
    ).strip()

    # Văn bản chưa chọn loại -> mở cho tất cả
    if not doc_type:
        return True

    emp = _user_employee(user)
    if not emp:
        return False
    emp_dept = frappe.db.get_value("Employee", emp, "department")

    # 1) Kiểm tra document đã load
    direct = {
        doc.employee,
        getattr(doc, "handler", None),
        getattr(doc, "nguoi_chu_tri", None),
        getattr(doc, "cv_xu_ly", None),
    }
    if emp in direct:
        return True
    if doc_type == "Công văn đi":
        if emp_dept and getattr(doc, "department", None) == emp_dept:
            return True
        if getattr(doc, "nguoi_ky", None) == emp:
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

    # 2.1) Thành viên HĐQT ở items6/items7
    for row in getattr(doc, "items6", []) or []:
        if getattr(row, "employee", None) == emp:
            return True
    for row in getattr(doc, "items7", []) or []:
        if getattr(row, "employee", None) == emp:
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
    if frappe.db.exists(
        "VNT Document Management Item6",
        {"parent": doc.name, "parenttype": doc.doctype, "parentfield": ["in", ["items6", "items7"]], "employee": emp},
    ):
        return True
    return bool(
        frappe.db.exists(
            "VNT Document Management Item",
            {"parent": doc.name, "parenttype": doc.doctype, "cv_xu_ly": emp},
        )
    )

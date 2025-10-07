import frappe
from frappe.model.document import Document
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.utils import getdate, add_days

class VNTBusinessTripRequest(Document):
    def before_submit(self):
        self.approval_status = "Đã duyệt"

    def after_insert(self):
        _notify_if_pending(self)

    def on_submit(self):
        # 1) Đóng ToDo liên quan
        close_todos_for_doc(self)
        # 2) Huỷ/xoá Attendance cũ và tạo mới (leave_type = "Công tác")
        replace_attendance_for_business_trip(self)

    def on_cancel(self):
        # 1) Xoá ToDo liên quan
        delete_todos_for_doc(self)
        # 2) Huỷ Attendance trong khoảng tương ứng
        cancel_attendance_for_trip(self)


# ---------------- ToDo ----------------
def close_todos_for_doc(doc: Document):
    """Đặt trạng thái ToDo -> Closed cho mọi ToDo của chứng từ."""
    names = frappe.get_all(
        "ToDo",
        filters={"reference_type": doc.doctype, "reference_name": doc.name, "status": ["!=", "Cancelled"]},
        pluck="name",
    )
    for n in names:
        frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)

def delete_todos_for_doc(doc: Document):
    """Xoá mọi ToDo của chứng từ khi Cancel."""
    names = frappe.get_all(
        "ToDo",
        filters={"reference_type": doc.doctype, "reference_name": doc.name},
        pluck="name",
    )
    for n in names:
        try:
            frappe.delete_doc("ToDo", n, ignore_permissions=True, force=1)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Không xoá được ToDo: {n}")


# --------------- Attendance ---------------
def _delete_or_cancel_attendance(employees: set, start_date, end_date):
    """Huỷ Submitted, xoá Draft Attendance trong khoảng."""
    existing = frappe.get_all(
        "Attendance",
        filters={
            "employee": ["in", list(employees)],
            "attendance_date": ["between", [start_date, end_date]],
            "docstatus": ["!=", 2],
        },
        fields=["name", "docstatus"],
    )
    for row in existing:
        try:
            att = frappe.get_doc("Attendance", row["name"])
            att.cancel() if att.docstatus == 1 else att.delete()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Không thể huỷ/xoá Attendance: {row['name']}")

def replace_attendance_for_business_trip(self: Document):
    """
    - Gom employee từ parent + child items (rỗng vẫn ok).
    - Huỷ/xoá Attendance cũ trong [from_date, to_date].
    - Tạo mới Attendance status='On Leave', leave_type='Công tác' (submit).
    """
    # 1) Employees
    employees = set()
    if self.get("employee"):
        employees.add(self.employee)
    for d in (self.items or []):
        if getattr(d, "employee", None):
            employees.add(d.employee)
    if not employees:
        return

    # 2) Dates
    if not self.get("from_date"):
        return
    start_date = getdate(self.from_date)
    end_date   = getdate(self.to_date or self.from_date)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    # 3) Dọn cũ
    _delete_or_cancel_attendance(employees, start_date, end_date)

    # 4) Tạo mới
    company = self.get("company")
    destination = self.get("destination") or ""
    d = start_date
    while d <= end_date:
        for emp in employees:
            att = frappe.new_doc("Attendance")
            att.employee = emp
            att.attendance_date = d
            att.status = "On Leave"
            att.leave_type = "Công tác"
            att.company = company or frappe.db.get_value("Employee", emp, "company")
            att.remarks = f"Công tác: {destination}" if destination else "Công tác"
            # Bật nếu muốn bỏ qua validate “is on Leave …”
            # att.flags.ignore_validate = True
            # att.flags.ignore_mandatory = True
            att.insert(ignore_permissions=True)
            att.submit()
        d = add_days(d, 1)

def cancel_attendance_for_trip(doc: Document):
    """Huỷ/xoá Attendance trong khoảng khi phiếu bị Cancel."""
    employees = set()
    if doc.get("employee"):
        employees.add(doc.employee)
    for d in (doc.items or []):
        if getattr(d, "employee", None):
            employees.add(d.employee)
    if not employees or not doc.get("from_date"):
        return

    start_date = getdate(doc.from_date)
    end_date   = getdate(doc.to_date or doc.from_date)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    _delete_or_cancel_attendance(employees, start_date, end_date)


# -------------- Notification --------------
def _notify_if_pending(doc: Document):
    # Thống nhất chuỗi trạng thái chờ duyệt
    if (doc.get("approval_status") in (None, "", "Chờ duyệt", "Chờ phê duyệt", "Pending")
        and doc.get("approver")):

        approver_user = get_employee_user_id(doc.approver)
        if not approver_user or approver_user == doc.owner:
            return

        notify_pending(doc, actor=doc.employee_name, receivers=[approver_user])
        ensure_todo(doc, approver_user)

def ensure_todo(doc: Document, user: str):
    """Tạo ToDo duyệt phiếu, không email, tránh trùng."""
    if not user:
        return
    if frappe.db.exists("ToDo", {
        "reference_type": doc.doctype,
        "reference_name": doc.name,
        "allocated_to": user,
        "status": ["!=", "Cancelled"],
    }):
        return

    destination = doc.get("destination") or _("(chưa xác định địa điểm)")
    employee = doc.get("employee_name") or _("(không rõ người tạo)")
    description = _("Duyệt phiếu đăng ký công tác tại {0}, do {1} tạo.").format(destination, employee)

    todo = frappe.get_doc({
        "doctype": "ToDo",
        "description": description,
        "allocated_to": user,
        "reference_type": doc.doctype,
        "reference_name": doc.name,
        "priority": "Medium",
        "status": "Open",
    })
    todo.insert(ignore_permissions=True)

def get_employee_user_id(employee_name: str) -> str | None:
    if not employee_name:
        return None
    return frappe.db.get_value("Employee", employee_name, "user_id")

def system_notification(message: str, doctype: str, docname: str, users: list[str] | None = None):
    if not users:
        return
    payload = {"type": "Alert", "subject": message, "document_type": doctype, "document_name": docname}
    make_notification_logs(payload, users)

def notify_pending(doc: Document, actor: str, receivers: list[str]):
    message = _("Phiếu đăng ký đi công tác của {0} đang chờ duyệt").format(actor or _("(không rõ)"))
    system_notification(message, doc.doctype, doc.name, receivers)

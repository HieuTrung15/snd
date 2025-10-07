import frappe
from frappe.model.document import Document
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.utils import getdate, add_days

# ---- Workflow states (khớp với ảnh) ----
PENDING_STATES = {"Chờ duyệt", "Chờ phê duyệt"}
APPROVED_STATE = "Đã duyệt"
REJECT_STATES  = {"Từ chối", "Huỷ", "Đã huỷ"}

class VNTBusinessTripRequest(Document):
    def on_update(self):
        if self.has_value_changed("approval_status"):
            _handle_state_transition(self)

    def on_submit(self):
        close_todos_for_doc(self)
        replace_attendance_for_business_trip(self)

    def on_cancel(self):
        delete_todos_for_doc(self)
        cancel_attendance_for_trip(self)

def _handle_state_transition(doc):
    state = (doc.get("approval_status") or "").strip()

    if state in {"Chờ duyệt", "Chờ phê duyệt"}:
        _notify_if_pending(doc)

    elif state == "Đã duyệt":
        return

    elif state in {"Từ chối", "Huỷ", "Đã huỷ"}:
        delete_todos_for_doc(doc)
        cancel_attendance_for_trip(doc)

# ---------------- ToDo ----------------
def close_todos_for_doc(doc: Document):
    names = frappe.get_all(
        "ToDo",
        filters={"reference_type": doc.doctype, "reference_name": doc.name, "status": ["!=", "Cancelled"]},
        pluck="name",
    )
    for n in names:
        frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)

def delete_todos_for_doc(doc: Document):
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

def ensure_todo(doc: Document, user: str):
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
    frappe.get_doc({
        "doctype": "ToDo",
        "description": description,
        "allocated_to": user,
        "reference_type": doc.doctype,
        "reference_name": doc.name,
        "priority": "Medium",
        "status": "Open",
    }).insert(ignore_permissions=True)

# ---------------- Notifications ----------------
def _notify_if_pending(doc: Document):
    approver = doc.get("approver")
    if not approver:
        return
    approver_user = get_employee_user_id(approver)
    if not approver_user or approver_user == doc.owner:
        return
    make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu đăng ký đi công tác của {0} đang chờ duyệt").format(doc.employee_name or _("(không rõ)")),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, [approver_user])
    ensure_todo(doc, approver_user)

def get_employee_user_id(employee_name: str) -> str | None:
    if not employee_name:
        return None
    return frappe.db.get_value("Employee", employee_name, "user_id")

# ---------------- Attendance ----------------
def _collect_employees(doc: Document) -> set:
    emps = set()
    if doc.get("employee"):
        emps.add(doc.employee)
    for d in (doc.items or []):
        if getattr(d, "employee", None):
            emps.add(d.employee)
    return emps

def _delete_or_cancel_attendance(employees: set, start_date, end_date):
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

def replace_attendance_for_business_trip(doc: Document):
    """
    ĐÚNG TÊN HÀM đang được gọi từ on_update/on_submit.
    - Gom employee từ parent + items.
    - Huỷ/xoá Attendance cũ trong [from_date, to_date].
    - Tạo mới Attendance status='On Leave', leave_type='Công tác' (submit).
    """
    employees = _collect_employees(doc)
    if not employees or not doc.get("from_date"):
        return

    start_date = getdate(doc.from_date)
    end_date   = getdate(doc.to_date or doc.from_date)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    # dọn cũ
    _delete_or_cancel_attendance(employees, start_date, end_date)

    # tạo mới
    company = doc.get("company")
    destination = doc.get("destination") or ""
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
            att.flags.ignore_validate = True
            att.flags.ignore_mandatory = True
            att.insert(ignore_permissions=True)
            att.submit()
        d = add_days(d, 1)

def cancel_attendance_for_trip(doc: Document):
    employees = _collect_employees(doc)
    if not employees or not doc.get("from_date"):
        return
    start_date = getdate(doc.from_date)
    end_date   = getdate(doc.to_date or doc.from_date)
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    _delete_or_cancel_attendance(employees, start_date, end_date)

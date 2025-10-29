import frappe
from frappe.model.document import Document
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.utils import getdate, add_days
import unicodedata

# ---------------- Utils ----------------
def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").strip()).lower()

def _in_state(state: str, states: set) -> bool:
    ns = _norm(state)
    return ns in {_norm(x) for x in states}

# ---- Workflow states ----
PENDING_STATES  = {"Chờ duyệt"}
APPROVED_STATES = {"Đã duyệt", "Duyệt"}
REJECT_STATES   = {"Từ chối", "Hủy", "Huỷ", "Đã hủy"}

class VNTBusinessTripRequest(Document):
    def on_update(self):
        _apply_state_effects(self)
        
    def on_update_after_submit(self):
        _apply_state_effects(self)

    def validate(self):
        if not self.from_date or not self.to_date:
            frappe.throw(_("Vui lòng nhập đầy đủ Từ ngày và Đến ngày"))

        fd, td = getdate(self.from_date), getdate(self.to_date)
        if fd > td:
            frappe.throw(_("Từ ngày không được lớn hơn Đến ngày"))

        conflict = frappe.db.sql(
            """
            SELECT name, from_date, to_date, workflow_state
            FROM `tabVNT Business Trip Request`
            WHERE employee = %(employee)s
              AND docstatus != 2
              AND name != %(name)s
              AND COALESCE(workflow_state, '') NOT IN %(states)s
              AND NOT (%(fd)s > to_date OR %(td)s < from_date)
            LIMIT 1
            """,
            {
                "employee": self.employee,
                "name": self.name,
                "fd": fd,
                "td": td,
                "states": REJECT_STATES,  # tuple/list OK
            },
            as_dict=True,
        )

        if conflict:
            c = conflict[0]
            frappe.throw(_(
                f"Nhân viên đã có phiếu công tác {c.name} "
                f"({c.workflow_state}) từ {c.from_date} đến {c.to_date}. "
                f"Không thể tạo thêm phiếu trùng thời gian."
            ))


# ---------------- State handling ----------------
def _apply_state_effects(doc: Document):
    state = doc.get("workflow_state") or ""

    if _in_state(state, PENDING_STATES):
        _notify_if_pending(doc)
        return

    if _in_state(state, APPROVED_STATES):
        close_todos_for_doc(doc)
        replace_attendance_for_business_trip(doc)
        _notify_employees_approved(doc)
        return

    if _in_state(state, REJECT_STATES):
        delete_todos_for_doc(doc)
        cancel_attendance_for_trip(doc)
        _notify_employees_rejected(doc)
        return

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
        "subject": _("Phiếu đăng ký đi công tác của {0} đang chờ duyệt").format(doc.employee_name),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, [approver_user])
    ensure_todo(doc, approver_user)

def _notify_employees_approved(doc: Document):
    users = _get_employee_user_ids(doc)
    if not users:
        return
    make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu công tác tại {0} đã được duyệt").format(doc.destination),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, users)

def get_employee_user_id(employee_name: str) -> str | None:
    if not employee_name:
        return None
    return frappe.db.get_value("Employee", employee_name, "user_id")

def _get_employee_user_ids(doc: Document) -> list[str]:
    employees = _collect_employees(doc)
    if not employees:
        return []
    users = set()
    for emp in employees:
        uid = frappe.db.get_value("Employee", emp, "user_id")
        if uid and uid != doc.owner:
            users.add(uid)
    return list(users)

# ---------------- Attendance ----------------
def _collect_employees(doc: Document) -> set:
    emps = set()
    if doc.get("employee"):
        emps.add(doc.employee)
    for d in (doc.items or []):
        emp = getattr(d, "employee", None)
        if emp:
            emps.add(emp)
    return emps

def _delete_or_cancel_attendance(employees: set, start_date, end_date):
    if not employees or not start_date or not end_date:
        return
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
            att.flags.ignore_permissions = True
            att.flags.ignore_links = True
            if att.docstatus == 1:
                att.cancel()
            else:
                frappe.delete_doc("Attendance", att.name, ignore_permissions=True, force=1)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Không thể huỷ/xoá Attendance: {row['name']}")

def replace_attendance_for_business_trip(doc: Document):
    if not _in_state(doc.get("workflow_state"), APPROVED_STATES):
        return

    employees = _collect_employees(doc)
    if not employees or not doc.get("from_date"):
        return

    start_date = getdate(doc.from_date)
    end_date   = getdate(doc.to_date or doc.from_date)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    # Idempotent
    _delete_or_cancel_attendance(employees, start_date, end_date)

    company = doc.get("company")
    destination = (doc.get("destination") or "").strip()

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


def _notify_employees_rejected(doc: Document):
    """Gửi Notification Log cho toàn bộ Employee thuộc phiếu khi bị từ chối."""
    users = _get_employee_user_ids(doc)
    if not users:
        return
    make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu công tác đã bị từ chối"),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, users)
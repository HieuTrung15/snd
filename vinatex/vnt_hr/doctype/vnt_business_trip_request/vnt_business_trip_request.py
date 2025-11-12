import frappe
from frappe.utils import getdate, add_days, nowdate, get_url_to_form
from frappe.model.document import Document
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
import unicodedata
from frappe.model.workflow import apply_workflow
from vinatex.patches.utils.rocket_chat import send_rocket_message

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

create_car_regis = [
    "Ô tô TĐ (trên 40 km)",
    "Ô tô TĐ (dưới 40 km)",
    "Ô tô (TĐ chịu chi phí)",
]

class VNTBusinessTripRequest(Document):
    def on_update(self):
        _apply_state_effects(self)


    def on_cancel(self):
        _check_emp_checkin_after_cancel(self)


    def on_update_after_submit(self):
        _apply_state_effects(self)

    def on_cancel(self):
        cancel_attendance_for_trip(self)
        cancel_vehicle_requests_for_trip(self)

    def validate(self):
        # danh sách phương tiện cần check
        targets = [
            "Ô tô TĐ (trên 40 km)",
            "Máy bay (Đơn vị trả chi phí)",
            "Máy bay (TĐ trả chi phí)",
        ]
        approver_lv2 = get_leave_approver_level_2(self.employee)
        self.approver_lv2 = approver_lv2[0]
        self.approver_name_lv2 = approver_lv2[1]
        # mặc định False
        self.check_vehicle_condition = 0

        # duyệt qua bảng con (vehicle)
        for row in self.vehicle or []:
            if row.vehicle_type in targets:
                self.check_vehicle_condition = 1
                break

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


def get_leave_approver_level_2(employee: str):
	# lấy approver trên Employee trước
	emp = frappe.db.get_value("Employee", employee, ["leave_approver", "department"], as_dict=True)
	if not emp:
		return None

	# nếu chưa có và có department → tìm trong Department Approver
	# ƯU TIÊN custom flag custom_level_2 = 1
	if emp:
		approver = frappe.db.get_value(
			"Department Approver",
			{
				"parent": emp.department,
				"parentfield": "leave_approvers",
				"custom_level_2": 1,      
			},
			["approver", "custom_approver_name"],
		)
	else :
		approver = emp.leave_approver

	return approver


def _get_prev_and_curr_workflow_state(doc: Document) -> tuple[str | None, str]:
	"""Trả về (previous_state, current_state) an toàn.
	- Ưu tiên lấy previous từ get_doc_before_save() nếu có.
	- Fallback lấy từ DB nếu chưa có trước đó (hoặc không ở on_update).
	"""
	prev_state = None
	try:
		before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
		if before:
			prev_state = (before.get("workflow_state") or "").strip()
	except Exception:
		prev_state = None
 
	if not prev_state and doc.get("name"):
		try:
			prev_state = (frappe.db.get_value(doc.doctype, doc.name, "workflow_state") or "").strip()
		except Exception:
			prev_state = None
 
	curr_state = (doc.get("workflow_state") or "").strip()
	return prev_state, curr_state


def _check_emp_checkin_after_cancel(doc: Document):
	"""kiểm tra nếu nhân viên đã có dữ liệu Employee Checkin trong khoảng nghỉ phép đã duyệt thì tạo attendance tương ứng."""
	# kiểm tra dữ liệu Attendance
	from frappe.utils import getdate
	attendance_records = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"attendance_date": ("between", [doc.from_date, doc.to_date]),
			"docstatus": 1,
			"status": ("in", ["Present", "Work From Home"]),
		},
		fields=["name", "attendance_date", "status"],
		order_by="attendance_date",
	)
	if attendance_records:
		return  # đã có attendance thì không tạo nữa
	# kiểm tra dữ liệu Employee Checkin
	employee_checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": doc.employee,
			"time": ("between", [str(doc.from_date) + " 00:00:00", str(doc.to_date) + " 23:59:59"]),
		},
		fields=["name", "time"],
		order_by="time",
	)
	if not employee_checkins:
		return  # không có dữ liệu checkin thì không làm gì
	# tạo attendance cho các ngày có checkin
	attendance_dates = set()
	for checkin in employee_checkins:
		checkin_date = getdate(checkin.time)
		attendance_dates.add(checkin_date)
	for att_date in attendance_dates:
		new_attendance = frappe.new_doc("Attendance")
		new_attendance.employee = doc.employee
		new_attendance.employee_name = doc.employee_name
		new_attendance.company = doc.company
		new_attendance.department = doc.department
		new_attendance.attendance_date = att_date
		new_attendance.status = "Present"
		new_attendance.docstatus = 1
		new_attendance.insert(ignore_permissions=True)
		frappe.db.commit()


# ---------------- State handling ----------------
def _apply_state_effects(doc: Document):
    prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)
    if prev_state == "Mới tạo" and curr_state == "Chờ lãnh đạo duyệt":
        _notify_if_pending(doc)
        return

    if prev_state == "Chờ lãnh đạo duyệt" and curr_state == "Chờ lãnh đạo tập đoàn duyệt":
        close_todos_for_doc(doc)
        _notify_if_pending_lv2(doc)

    if prev_state == "Chờ lãnh đạo duyệt" and curr_state == "Đã duyệt" :
        close_todos_for_doc(doc)
        replace_attendance_for_business_trip(doc)
        _notify_to_employee_list(doc)
        return
    
    if prev_state == "Chờ lãnh đạo tập đoàn duyệt" and curr_state == "Đã duyệt":
        close_todos_for_doc(doc)
        replace_attendance_for_business_trip(doc)
        _notify_to_employee_list_2(doc)
        return
    
    if prev_state == "Chờ lãnh đạo duyệt" and curr_state == "Từ chối" \
        or prev_state == "Chờ lãnh đạo tập đoàn duyệt" and curr_state == "Từ chối":
        _notify_employees_rejected(doc)
        return

    if prev_state == "Đã duyệt" and curr_state == "Hủy":
        # delete_todos_for_doc(doc)
        cancel_attendance_for_trip(doc)
        cancel_vehicle_requests_for_trip(doc)
        _notify_employees_cancelled(doc)
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


def _notify_if_pending_lv2(doc: Document):
    approver = doc.get("approver_lv2")
    if not approver:
        return
    if not approver or approver == doc.owner:
        return
    make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu đăng ký đi công tác của {0} đang chờ duyệt.").format(doc.employee_name),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, [approver])
    ensure_todo(doc, approver)


# gửi thông báo đến emp tham gia chuyến xe
def _notify_to_employee_list(doc):
	"""Gửi thông báo đến nhân viên tạo phiếu và danh sách nhân sự trong items khi đơn được lãnh đạo duyệt."""
	_send_trip_notification(
		doc,
		_("Đơn đi công tác của {0} từ ngày {1} đến ngày {2} đã được lãnh đạo duyệt").format(
			doc.employee_name or _("(không rõ)"), doc.from_date, doc.to_date
		),
	)


def _notify_to_employee_list_2(doc):
    """Gửi thông báo đến nhân viên tạo phiếu và danh sách nhân sự trong items khi đơn được lãnh đạo tập đoàn duyệt."""
    _send_trip_notification(
        doc,
        _("Đơn đi công tác của {0} từ ngày {1} đến ngày {2} đã được lãnh đạo tập đoàn duyệt.").format(
            doc.employee_name or _("(không rõ)"), doc.from_date, doc.to_date
        ),
    )


def _send_trip_notification(doc: Document, subject: str):
    employees = _collect_employees(doc)
    if not employees:
        return

    users = set()
    for emp in employees:
        user = get_employee_user_id(emp)
        if user:
            users.add(user)

    if not users:
        return
    make_notification_logs({
        "type": "Alert",
        "subject": subject,
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, list(users))


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

    # tạo attendance
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

    # tạo đăng ký xe nếu có phương tiện thuộc danh sách yêu cầu đăng ký xe
    item_val = [row.as_dict() for row in doc.transportation]
    transportation_rows = []
    for row in item_val:
        vehicle_item = (getattr(row, "vehicle_item", "") or "")
        if vehicle_item in create_car_regis:
            transportation_rows.append(row)
    # frappe.throw(f"{transportation_rows}")
    if transportation_rows:
        create_vehicle_request_for_business_trip(doc, transportation_rows)

    list_vehicle = [row.as_dict() for row in doc.vehicle]
    result = any(r.get("vehicle_type") == "Máy bay (TĐ trả chi phí)" for r in list_vehicle)

    # nếu có máy báy gửi thông báo đến quản lý văn phòng
    if result:
        _notify_to_office_manager(doc)


def _notify_to_office_manager(doc: Document):
	"""Gửi thông báo đến những members trong User Group 'Nhận thông báo đăng ký xin xe' khi đơn được duyệt."""
	user_group_name = "Nhận thông báo đăng ký xin xe"
	user_list = frappe.get_all(
		"User Group Member",
		filters={"parent": user_group_name},
		pluck="user",
	)

	if not user_list:
		return
	make_notification_logs({
		"type": "Alert",
		"subject": _("Công tác của {0} cần vé máy bay. Vui lòng kiểm tra.").format(doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, user_list)


def create_vehicle_request_for_business_trip(doc: Document, transportation_rows: list):
    if not transportation_rows:
        return

    existing_name = frappe.db.get_value(
        "VNT Car Registration",
        {"business_trip": doc.name, "docstatus": ["!=", 2]},
        "name",
    )

    if existing_name:
        vehicle_request = frappe.get_doc("VNT Car Registration", existing_name)
        vehicle_request.flags.ignore_permissions = True
        vehicle_request.flags.ignore_validate_update_after_submit = True
        vehicle_request.set("items", [])
    else:
        vehicle_request = frappe.new_doc("VNT Car Registration")
        vehicle_request.business_trip = doc.name

    vehicle_request.employee = doc.employee
    vehicle_request.employee_name = doc.employee_name
    vehicle_request.company = doc.company
    vehicle_request.department = doc.department
    vehicle_request.branch = doc.branch
    # vehicle_request.distance = doc.distance
    vehicle_request.note = doc.purpose
    # approver_user = get_employee_user_id(doc.approver)
    vehicle_request.approver = doc.approver
    vehicle_request.company = doc.company

    employees = sorted(_collect_employees(doc))
    vehicle_request.set("list_emp", [])
    for emp in employees:
        vehicle_request.append("list_emp", {"employee": emp})

    for row in transportation_rows:
        vehicle_request.append(
            "items",
            {
                "start": row.start,
                "end": row.end,
                "time": row.time,
                "date": row.date,
                "note": row.note
            },
        )
    vehicle_request.docstatus = 1
    vehicle_request.worlflow_state = "Đã duyệt"
    vehicle_request.insert(ignore_permissions=True)
    frappe.db.commit()

    # gửi thông báo cho ngườ điều xe (1 người)
    # tạo bản ghi mới trong vnt vehicle control hoặc cập nhật nếu đã có
    user_group_name = "Nhận thông báo điều xe"
    user_list = frappe.get_all(
        "User Group Member",
        filters={"parent": user_group_name},
        pluck="user",
    )
    if not user_list:
        return

    employee_user = frappe.get_value('User', {'name': user_list[0]}, 'full_name')
    vehicle_control_name = frappe.db.get_value(
        "VNT Vehicle Control Item",
        {"id_parent": vehicle_request.name},
        "parent",
    )

    if vehicle_control_name:
        vehicle_control = frappe.get_doc("VNT Vehicle Control", vehicle_control_name)
        vehicle_control.flags.ignore_permissions = True
        vehicle_control.set("items", [])
    else:
        vehicle_control = frappe.new_doc("VNT Vehicle Control")
        vehicle_control.set("date", nowdate())

    vehicle_control.employee_name = employee_user

    for item in vehicle_request.get("items") or []:
        vehicle_control.append(
            "items",
            {
                "employee_name": doc.employee_name,
                "start": item.start,
                "end": item.end,
                "time": item.time,
                "date": item.date,
                "id_parent": vehicle_request.name,
                "id_child": item.name,
            },
        )

    if vehicle_control_name:
        vehicle_control.save(ignore_permissions=True)
    else:
        vehicle_control.insert(ignore_permissions=True)

    make_notification_logs({
        "type": "Alert",
        "subject": _("Vui lòng điều xe cho phiếu đăng ký xe của {0} đã được duyệt.").format(doc.employee_name or _("(không rõ)")),
        "document_type": 'VNT Vehicle Control',
        "document_name": vehicle_control.name,
    }, user_list)
    # tạo todo cho người điều xe
    ensure_todo(vehicle_control, user_list[0])
    if frappe.db.exists("ToDo", {
        "reference_type": doc.doctype,
        "reference_name": doc.name,
        "allocated_to": user_list[0],
        "status": ["!=", "Cancelled"],
    }):
        return
    description = _("Vui lòng điều xe cho phiếu đăng ký xe của {0} đã được duyệt.").format(doc.employee_name or _("(không rõ)"))
    frappe.get_doc({
        "doctype": "ToDo",
        "description": description,
        "allocated_to": user_list[0],
        "reference_type": "VNT Vehicle Control",
        "reference_name": vehicle_control.name,
        "priority": "Medium",
        "status": "Open",
    }).insert(ignore_permissions=True)


def cancel_attendance_for_trip(doc: Document):
    employees = _collect_employees(doc)
    if not employees or not doc.get("from_date"):
        return
    start_date = getdate(doc.from_date)
    end_date   = getdate(doc.to_date or doc.from_date)
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    _delete_or_cancel_attendance(employees, start_date, end_date)

def cancel_vehicle_requests_for_trip(doc: Document):
    """Update linked car registrations when the trip is rejected or cancelled."""
    if not doc.get("name"):
        return
    names = frappe.get_all(
        "VNT Car Registration",
        filters={
            "business_trip": doc.name,
            "docstatus": ["!=", 2],
        },
        pluck="name",
    )
    for name in names:
        try:
            car_doc = frappe.get_doc("VNT Car Registration", name)
            car_doc.flags.ignore_permissions = True
            car_doc.flags.ignore_validate_update_after_submit = True
            cancle_state = "Đã hủy"
            
            if (car_doc.workflow_state or "").strip() != cancle_state or car_doc.workflow_state == "Đã duyệt":
                car_doc.workflow_state = cancle_state
                car_doc.cancel()
                car_doc.save(ignore_permissions=True)
            # frappe.throw(car_doc.workflow_state)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Không thể cập nhật phiếu đăng ký xe liên kết {name} của phiếu công tác {doc.name}",
            )


def _notify_employees_rejected(doc: Document):
    """Gửi Notification Log cho toàn bộ Employee thuộc phiếu khi bị từ chối."""
    users = _get_employee_user_ids(doc)
    if not users:
        return
    make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu công tác đã bị từ chối."),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, users)


def _notify_employees_cancelled(doc: Document):
    """Gửi Notification Log cho toàn bộ Employee thuộc phiếu khi bị hủy."""
    users = _get_employee_user_ids(doc)
    if not users:
        return
    make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu công tác đã bị hủy."),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, users)


@frappe.whitelist()
def get_employee(employee):
    user_id = frappe.db.get_value("Employee", employee, ["employee_name", "department", "designation", "salutation"], as_dict=True)
    return user_id

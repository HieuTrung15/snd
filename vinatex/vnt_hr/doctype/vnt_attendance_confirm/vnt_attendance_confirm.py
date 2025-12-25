# # Copyright (c) 2025, vinatex and contributors
# # For license information, please see license.txt

from calendar import monthrange
from datetime import datetime, time, date, timedelta

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.model.document import Document
from frappe.utils import getdate, get_url_to_form
# from hrms.hr.utils import get_holiday_list_for_employee(employee)
from vinatex.patches.utils.rocket_chat import send_rocket_message


class VNTAttendanceConfirm(Document):
	def on_submit(self):
		_cron_submit_attendance_confirm()


	def on_update(self):
		# nếu các dòng trong items có giải trình và không có phê duyệt thì gửi thông báo đến người duyệt
		items = self.get("items") or []
		all_types_filled = all(row.get("type") for row in items) if items else False
		pending = [row for row in items if row.get("type") and not row.get("confirm")]
		if all_types_filled and pending:
			_notify_approver_pending(self)
			_close_employee_todos(self)

		type_confirm = [row.get("type") for row in (self.get("items") or []) if row.get("confirm")]
		if type_confirm:
			_make_attendance_from_confirmation(self)
			_reject_attendance_from_confirmation(self)
			if not pending:
				_close_approver_todos(self)

	def on_cancel(self):
		_cancel_attendance_from_confirmation(self)


def _employee_user_id(employee: str | None) -> str | None:
	if not employee:
		return None
	return frappe.db.get_value("Employee", employee, "user_id")


def _resolve_employee_user(doc: Document) -> str | None:
	user = _employee_user_id(doc.employee)
	if user:
		return user
	raw = doc.get("email")
	if raw and frappe.db.get_value("Employee", {"user_id": raw}, "name") == doc.employee:
		return raw
	return None


def _resolve_approver_user(doc: Document) -> str | None:
	user = _employee_user_id(doc.approver)
	if user:
		return user
	raw = doc.get("email")
	if raw and frappe.db.get_value("Employee", {"user_id": raw}, "name") == doc.approver:
		return raw
	return None


def _send_notification(doc: Document, user: str | list[str] | tuple[str, ...], subject: str, message: str):
	if isinstance(user, (list, tuple, set)):
		target_users = {u for u in user if u}
	elif user:
		target_users = {user}
	else:
		target_users = set()

	if not target_users:
		return

	recipients = list(target_users)
	make_notification_logs({
		"type": "Alert",
		"subject": subject,
		"document_type": doc.doctype,
		"document_name": doc.name,
		"message": message,
	}, recipients)
	send_rocket_message(
		to_users=recipients,
		title=":bell: Thông báo",
		message=f"*{subject}*\n{message}" if message else subject,
		link=get_url_to_form(doc.doctype, doc.name),
	)


def _normalize_confirmation_dates(dates: list[date] | None = None) -> list[date]:
	if not dates:
		return []
	norm = []
	for d in dates:
		if not d:
			continue
		norm.append(getdate(d))
	return sorted(set(norm))


def _format_date_value(value: date | None) -> str:
	if not value:
		return _("(chưa rõ)")
	return frappe.format_value(value, {"fieldtype": "Date"})


def _ensure_todo_for_confirmation(doc: Document, user: str, dates: list[date] | None = None):
	if not user:
		return
	mapped_employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if mapped_employee and mapped_employee != doc.employee:
		return
	norm_dates = _normalize_confirmation_dates(dates)
	first_item_date = None
	if doc.get("items"):
		first_item_date = getdate(doc.items[0].get("date")) if doc.items[0].get("date") else None

	start_date = first_item_date or (norm_dates[0] if norm_dates else (getdate(doc.from_date) if doc.from_date else None))
	end_date = norm_dates[-1] if norm_dates else (getdate(doc.to_date) if doc.to_date else start_date)
	start_label = _format_date_value(start_date)
	end_label = _format_date_value(end_date)
	pending_count = len([row for row in (doc.get("items") or []) if not row.get("type")])
	days_count = pending_count or (len(norm_dates) if norm_dates else 0)
	days_count = days_count or 1  # tối thiểu 1 ngày để tránh hiển thị (0 ngày)

	description = _("Xác nhận chấm công từ {0} đến {1} ({2} ngày) của {3}").format(
		start_label, end_label, days_count, doc.employee_name or doc.employee or _("Nhân viên")
	)

	existing = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"allocated_to": user,
			"status": ["!=", "Cancelled"],
		},
		pluck="name",
		limit=1,
	)
	if existing:
		# Cập nhật mô tả và đảm bảo ở trạng thái mở thay vì tạo dòng trùng.
		frappe.db.set_value(
			"ToDo",
			existing[0],
			{"description": description, "status": "Open"},
		)
		return

	new_todo = frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = "Medium"
	new_todo.status = "Open"
	new_todo.insert()
	frappe.db.commit()


def _notify_confirmation(doc: Document, user: str, dates: list[date] | None = None):
	if not user:
		return
	norm_dates = _normalize_confirmation_dates(dates)
	start_date = norm_dates[0] if norm_dates else (getdate(doc.from_date) if doc.from_date else None)
	end_date = norm_dates[-1] if norm_dates else (getdate(doc.to_date) if doc.to_date else start_date)
	start_label = _format_date_value(start_date)
	end_label = _format_date_value(end_date)
	subject = _("Xác nhận chấm công ngày {0} của {1}").format(end_date, doc.employee_name or doc.employee or _("Nhân viên"))
	if norm_dates and len(norm_dates) == 1:
		message = _("Có chấm công bất thường của {0} ngày {1}.").format(
			frappe.format_value(doc.employee_name, {"fieldtype": "Data"}) if doc.employee_name else _("(chưa rõ)"),
			start_label,
		)
	else:
		message = _("Có chấm công bất thường của {0} từ {1} đến {2}.").format(
			frappe.format_value(doc.employee_name, {"fieldtype": "Data"}) if doc.employee_name else _("(chưa rõ)"),
			start_label,
			end_label,
		)

	mapped_employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if mapped_employee and mapped_employee != doc.employee:
		return
	# _ensure_todo_for_confirmation(doc, user, norm_dates)
	_send_notification(doc, user, subject, message)
 

def _reject_attendance_from_confirmation(doc: Document):
	# Từ chối tạo Attendance cho các ngày trong items
	att_check = False
	for row in doc.get("items") or []:
		att_check = row.get("type") and row.get("confirm") == "Từ chối"
	if att_check:
		_notify_reject_employee_result(doc)


def _notify_reject_employee_result(doc: Document):
	user = _resolve_employee_user(doc)
	if not user:
		return

	subject = _("Bảng xác nhận chấm công đã bị từ chối")
	message = _("Bảng chấm công từ {0} đến {1} đã bị từ chối.").format(
		frappe.format_value(doc.from_date, {"fieldtype": "Date"}) if doc.from_date else _("(chưa rõ)"),
		frappe.format_value(doc.to_date, {"fieldtype": "Date"}) if doc.to_date else _("(chưa rõ)"),
	)

	_send_notification(doc, user, subject, message)



def _make_attendance_from_confirmation(doc: Document):
	# Tạo Attendance cho các ngày trong items
	created = False
	for row in doc.get("items") or []:
		att_check = row.get("type") and row.get("confirm") == "Đồng ý"
		if not att_check:
			continue
		existing_att = frappe.db.exists("Attendance", {
		"employee": doc.employee,
		"attendance_date": row.get("date"),
		"docstatus": ["=", 1],
			})
		if existing_att:
			continue
		# Tạo mới attendance
		att = frappe.get_doc({
			"doctype": "Attendance",
			"employee": doc.employee,
			"employee_name": doc.employee_name,
			"company": frappe.db.get_value("Employee", doc.employee, "company"),
			"attendance_date": row.get("date"),
			"status": "Present",
			"shift": "Hành chính",
			"docstatus": 1,
		})
		att.insert()
		created = True
	if created:
		_notify_employee_result(doc)


def _notify_employee_result(doc: Document):
	user = _resolve_employee_user(doc)
	if not user:
		return

	subject = _("Bảng xác nhận chấm công đã được duyệt.")
	message = _("Bảng chấm công từ {0} đến {1} đã được duyệt.").format(
		frappe.format_value(doc.from_date, {"fieldtype": "Date"}) if doc.from_date else _("(chưa rõ)"),
		frappe.format_value(doc.to_date, {"fieldtype": "Date"}) if doc.to_date else _("(chưa rõ)"),
	)

	_send_notification(doc, user, subject, message)


def _cancel_attendance_from_confirmation(doc: Document):
	for row in doc.get("items") or []:
		existing_att = frappe.db.exists("Attendance", {
		"employee": doc.employee,
		"attendance_date": row.get("date"),
		"docstatus": ["=", 1],
			})
		if existing_att:
			frappe.db.set_value("Attendance", existing_att, "docstatus", 2)
	_notify_cancel_employee_result(doc)


def _notify_approver_pending(doc: Document):
	emp = doc.get("approver")
	user = _employee_user_id(emp)
	if not user or not doc.items:
		return

	subject = _("Phê duyệt giải trình chấm công: {0}").format(doc.employee_name or doc.employee or _("Nhân viên"))
	message = _(
		"{0} đã gửi bảng chấm công từ {1} đến {2}.")
	message = message.format(
		doc.employee_name or doc.employee or _("Nhân viên"),
		frappe.format_value(doc.from_date, {"fieldtype": "Date"}) if doc.from_date else _("(chưa rõ)"),
		frappe.format_value(doc.to_date, {"fieldtype": "Date"}) if doc.to_date else _("(chưa rõ)"),
	)
	_ensure_todo_for_approver(doc, user, subject)
	_send_notification(doc, user, subject, message)


def _ensure_todo_for_approver(doc: Document, user: str, description: str):
	existing = frappe.db.get_value(
		"ToDo",
		{
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"allocated_to": user,
			"status": ["!=", "Cancelled"],
		},
		"name",
	)
	if existing:
		frappe.db.set_value(
			"ToDo",
			existing,
			{"description": description, "status": "Open"},
		)
		return

	new_todo = frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = "Medium"
	new_todo.status = "Open"
	new_todo.insert()
	frappe.db.commit()


def _close_employee_todos(doc: Document):
	employee_user = _resolve_employee_user(doc)
	if not employee_user:
		return
	names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"allocated_to": employee_user,
			"status": ["!=", "Cancelled"],
		},
		pluck="name",
	)
	for n in names:
		frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


def _close_approver_todos(doc: Document):
	approver_user = _resolve_approver_user(doc)
	if not approver_user:
		return
	names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"allocated_to": approver_user,
			"status": ["!=", "Cancelled"],
		},
		pluck="name",
	)
	for n in names:
		frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


def _notify_cancel_employee_result(doc: Document):
	user = _resolve_employee_user(doc)
	if not user:
		return

	subject = _("Bảng xác nhận chấm công đã bị hủy.")
	message = _(
		"Bảng chấm công từ {0} đến {1} bị hủy.")
	message = message.format(
		frappe.format_value(doc.from_date, {"fieldtype": "Date"}) if doc.from_date else _("(chưa rõ)"),
		frappe.format_value(doc.to_date, {"fieldtype": "Date"}) if doc.to_date else _("(chưa rõ)"),
	)

	_send_notification(doc, user, subject, message)


@frappe.whitelist()
def _cron_submit_attendance_confirm():
	emps = _pick_employees(None)
	"""Tìm các phiếu chấm công của từng employee, điền giá trị type = 'OK' và confirm = 'Đồng ý' cho các ngày chưa có giá trị. Sau đó submit phiếu.	"""
	for emp in emps:
		emp_name = emp["name"]
		# Tìm phiếu tháng hiện tại (docstatus=1)
		att_name = frappe.db.get_value(
			"VNT Attendance Confirm",
			{
				"employee": emp_name,
				"from_date": getdate(datetime.today().replace(day=1)),
				"docstatus": 1,
			},
			"name",
		)
		if not att_name:
			continue
		att = frappe.get_doc("VNT Attendance Confirm", att_name)
		changed = False
		for row in att.get("items") or []:
			if not row.get("type"):
				row.type = "OK"
				row.confirm = "Đồng ý"
				changed = True
		if changed:
			att.save()
			att.submit()


def get_reports_to(user):
	return frappe.get_value("Employee", {"name": user}, "employee_name")
	

@frappe.whitelist()
def make_attendance_confirm():
	# Upsert 1 phiếu/tháng cho mỗi nhân viên và thêm/cập nhật items theo từng ngày
	working_days = get_working_dates_of_month()
	if not working_days:
		return []

	month_from, month_to = min_max_date(working_days)
	# Lấy NV áp dụng
	emps = _pick_employees(None)

	# Chuẩn bị dữ liệu chấm công/leaves trong khoảng đầu tháng -> hôm nay
	t0, _ = _day_bounds(month_from)
	_, t1 = _day_bounds(month_to)
	checkins_map = _bulk_fetch_checkins(emps, t0, t1)
	leaves_set = _bulk_fetch_leaves(emps, t0, t1)
	trip_set = _bulk_fetch_trip(emps, t0, t1)
	attendance_set = _bulk_fetch_attendance(emps, t0, t1)

	results = []
	for emp in emps:
		emp_name = emp["name"]
		approver_emp = get_reports_to(emp["reports_to"])
		# Tìm phiếu tháng hiện tại (docstatus<2)
		att_name = frappe.db.get_value(
			"VNT Attendance Confirm",
			{
				"employee": emp_name,
				"from_date": month_from,
				"docstatus": ["<", 2],
			},
			"name",
		)

		is_new = False
		if att_name:
			att = frappe.get_doc("VNT Attendance Confirm", att_name)
		else:
			# Tạo mới nếu chưa có
			att = frappe.new_doc("VNT Attendance Confirm")
			att.employee = emp_name
			att.employee_name = emp.get("employee_name")
			att.department = emp.get("department")
			att.email = emp.get("user_id")
			att.from_date = month_from
			att.approver = emp.get("reports_to") or None
			att.approver_name = approver_emp or None
			# att.docstatus = 1
			is_new = True

		# Cập nhật to_date đến ngày hiện tại của tháng
		if not att.get("to_date") or getdate(att.to_date) != month_to:
			att.to_date = month_to

		# Lập chỉ mục items theo ngày để update nhanh
		existing_by_date = {getdate(r.get("date")): r for r in (att.get("items") or [])}

		changed = False
		added_dates: list[date] = []
		for d in working_days:
			key = (emp_name, d)
			row = existing_by_date.get(d)

			if key in attendance_set:
				# if row:
				# 	att.remove(row)
				# 	existing_by_date.pop(d, None)
				# 	changed = True
				continue
			# Tính status + thời gian vào/ra
			if key in leaves_set:
				# Bỏ qua hoàn toàn ngày có Leave Application: không tạo item
				continue
			elif key in trip_set:
				# Bỏ qua hoàn toàn ngày có Business Trip: không tạo item
				continue
			else:
				rec = checkins_map.get(key, {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})
				fi, lo = rec["first_in"], rec["last_out"]
				ci, co = rec["cnt_in"],  rec["cnt_out"]

				status = "OK"
				issues = []
				SHIFT_START = time(8, 15)
				SHIFT_END   = time(17, 0)

				if ci == 0 and co == 0:
					status = "Vắng mặt"
				elif ci > 0 and co == 0:
					if fi and fi.time() > SHIFT_START:
						issues.append("Đi muộn")
					issues.append("Quên chấm công")
				elif co > 0 and ci == 0:
					issues.append("Quên chấm công")
					if lo and lo.time() < SHIFT_END:
						issues.append("Về sớm")
				else:
					if fi and fi.time() > SHIFT_START:
						issues.append("Đi muộn")
					if lo and lo.time() < SHIFT_END:
						issues.append("Về sớm")

				if issues:
					status = ", ".join(issues)

				# Bỏ qua ngày status OK: không tạo/cập nhật item
				if status == "OK":
					continue

			# Giá trị time theo chuỗi HH:MM:SS để khớp field Time
			v_in  = fi.strftime("%H:%M:%S") if fi else None
			v_out = lo.strftime("%H:%M:%S") if lo else None

			if row:
				# Update only when values changed
				if (row.get("time_in") != v_in) or (row.get("time_out") != v_out) or (row.get("status") != status):
					row.time_in = v_in
					row.time_out = v_out
					row.status = status
					changed = True
			else:
				att.append("items", {
					"date": d,
					"time_in": v_in,
					"time_out": v_out,
					"status": status,
				})
				changed = True
				added_dates.append(d)

		user = _resolve_employee_user(att)
		if is_new:
			att.insert()
			if added_dates:
				_ensure_todo_for_confirmation(att, user, added_dates)
				_notify_confirmation(att, user, added_dates)
			results.append(att.name)
		elif changed:
			att.save()
			if added_dates:
				_ensure_todo_for_confirmation(att, user, added_dates)
				_notify_confirmation(att, user, added_dates)
			results.append(att.name)
	return results


@frappe.whitelist()
def get_working_dates_of_month():
	# lấy ra các ngày làm việc trong tháng đang xét (đã loại bỏ holiday).
	# Nếu đang là mùng 1 thì quay về trọn tháng trước, ngược lại lấy từ đầu tháng đến hôm qua.
	today = date.today()
	year = today.year
	month = today.month
	holiday_list = None
	company = frappe.defaults.get_user_default("Company")
	if company:
		holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
	if not holiday_list:
		frappe.throw("Không xác định được Holiday List (thiếu employee/company/holiday_list).")

	if today.day == 1:
	# Lấy tháng trước
		prev_month = month - 1 if month > 1 else 12
		prev_year = year if month > 1 else year - 1
		start_date = date(prev_year, prev_month, 1)
		end_date = date(prev_year, prev_month, monthrange(prev_year, prev_month)[1])
	else:
		start_date = date(year, month, 1)
		end_date = today - timedelta(days=1)

	if end_date < start_date:
		return []

	# Lấy toàn bộ holiday trong khoảng và đưa vào set để tra nhanh
	holidays = frappe.get_all(
		"Holiday",
		filters={
			"parent": holiday_list,
			"holiday_date": ["between", [start_date, end_date]],
		},
		pluck="holiday_date",  # trả về list các date
	)
	holiday_set = set(holidays)  # O(1) lookup
 
	# Sinh danh sách ngày và loại bỏ holiday
	days = (end_date - start_date).days + 1
	working_dates = [
		(start_date + timedelta(days=i))
		for i in range(days)
		if (start_date + timedelta(days=i)) not in holiday_set
	]
	return working_dates


def _day_bounds(d):
	return datetime.combine(d, time.min), datetime.combine(d, time.max)

def _parse_dates(dates):
	"""dates: list[str 'YYYY-MM-DD'] -> list[date]; bỏ trùng & sort"""
	ds = sorted({getdate(x) for x in dates})
	return ds

def _pick_employees(employees):
	"""Trả về list dict nhân viên có các field cần thiết.
	- Nếu employees là list mã NV -> lọc theo danh sách đó
	- Nếu None -> lấy toàn bộ NV Active và custom_need_check=0
	"""
	fields = ["name", "employee_name", "department", "user_id", "leave_approver", "reports_to"]
	if employees:
		return frappe.get_all(
			"Employee",
			filters={"status": "Active", "name": ["in", employees], "custom_need_check": 0, "attendance_device_id": ["!=", None]},
			fields=fields,
		)
	return frappe.get_all("Employee", filters={"status": "Active", "custom_need_check": 0,"attendance_device_id": ["!=", None]}, fields=fields)

def _emp_names(employees):
	"""employees: list[dict|str] -> tuple tên nhân viên"""
	if not employees:
		return tuple()
	if isinstance(employees[0], dict):
		return tuple(e["name"] for e in employees)
	return tuple(employees)


def _bulk_fetch_checkins(employees, d_start, d_end):
	"""Lấy IN sớm nhất và OUT muộn nhất theo (emp, date) trong khoảng d_start..d_end (datetime)."""
	if not employees:
		return {}

	emps = _emp_names(employees)
	# d_start/d_end PHẢI là datetime (đầu ngày/cuối ngày)
	rows = frappe.db.sql(
		"""
		SELECT employee, log_type, time
		FROM `tabEmployee Checkin`
		WHERE employee IN %(emps)s
		  AND time BETWEEN %(t0)s AND %(t1)s
		""",
		{"emps": emps, "t0": d_start, "t1": d_end},
		as_dict=True,
	)
	box = {}
	for r in rows:
		emp = r["employee"]
		d   = getdate(r["time"])
		key = (emp, d)
		item = box.setdefault(key, {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})

		if r["log_type"] == "IN":
			item["cnt_in"] += 1
			if item["first_in"] is None or r["time"] < item["first_in"]:
				item["first_in"] = r["time"]
		elif r["log_type"] == "OUT":
			item["cnt_out"] += 1
			if item["last_out"] is None or r["time"] > item["last_out"]:
				item["last_out"] = r["time"]
	return box


def _bulk_fetch_attendance(employees, d_start, d_end):
	"""Trả về set[(emp, date)] cho các ngày đã có Attendance (docstatus != Cancelled)."""
	if not employees:
		return set()

	emps = _emp_names(employees)
	rows = frappe.db.sql(
		"""
		SELECT employee, attendance_date
		FROM `tabAttendance`
		WHERE employee IN %(emps)s
		  AND attendance_date BETWEEN %(d0)s AND %(d1)s
		  AND docstatus != 2
		""",
		{"emps": emps, "d0": d_start.date(), "d1": d_end.date()},
		as_dict=True,
	)
	return {(r["employee"], getdate(r["attendance_date"])) for r in rows}


def _bulk_fetch_leaves(employees, d_start, d_end):
	"""Trả về set[(emp, date)] cho các ngày có đơn nghỉ (không Rejected/Cancelled)."""
	if not employees:
		return set()

	emps = _emp_names(employees)
	leaves = frappe.db.sql(
		"""
		SELECT employee, from_date, to_date
		FROM `tabLeave Application`
		WHERE employee IN %(emps)s
		  AND to_date   >= %(d0)s
		  AND from_date <= %(d1)s
		  AND workflow_state IN ('Đã duyệt')
		""",
		{"emps": emps, "d0": d_start.date(), "d1": d_end.date()},
		as_dict=True,
	)

	covered = set()
	for r in leaves:
		emp = r["employee"]
		d0  = getdate(r["from_date"])
		d1  = getdate(r["to_date"])
		cur = d0
		while cur <= d1:
			if d_start.date() <= cur <= d_end.date():
				covered.add((emp, cur))
			cur += timedelta(days=1)
	return covered


def _bulk_fetch_trip(employees, d_start, d_end):
	"""Trả về set[(emp, date)] cho các ngày có đơn đi công tác (không Rejected/Cancelled)."""
	if not employees:
		return set()

	emps = _emp_names(employees)
	trips = frappe.db.sql(
		"""
		SELECT employee, from_date, to_date
		FROM `tabVNT Business Trip Request`
		WHERE employee IN %(emps)s
		  AND to_date   >= %(d0)s
		  AND from_date <= %(d1)s
		  AND workflow_state IN ('Đã duyệt')
		""",
		{"emps": emps, "d0": d_start.date(), "d1": d_end.date()},
		as_dict=True,
	)

	covered = set()
	for r in trips:
		emp = r["employee"]
		d0  = getdate(r["from_date"])
		d1  = getdate(r["to_date"])
		cur = d0
		while cur <= d1:
			if d_start.date() <= cur <= d_end.date():
				covered.add((emp, cur))
			cur += timedelta(days=1)
	return covered


def min_max_date(dates):
	# lọc None nếu có
	dates = [d for d in dates if d]
	if not dates:
		return None, None
	return min(dates), max(dates)


# @frappe.whitelist()
# def check_employee_checkin_by_days(employees=None):
#     """
#     Tính trạng thái chấm công theo ngày trong tháng đến hôm nay (đã trừ holiday).
#     Chỉ trả về các dòng có vấn đề (status != 'OK').
#     """
#     working_days = get_working_dates_of_month()
#     from_date, to_date = min_max_date(working_days)
#     days = _parse_dates(working_days)
#     if not days:
#         return []
 
#     emps = _pick_employees(employees)
 
#     # Giờ chuẩn ca
#     shift_start = "08:15"
#     shift_end   = "17:00"
#     h1, m1 = map(int, shift_start.split(":"))
#     h2, m2 = map(int, shift_end.split(":"))
#     SHIFT_START = time(h1, m1)
#     SHIFT_END   = time(h2, m2)
 
#     # Khoảng thời gian đúng (đầu/cuối ngày) để bulk-fetch
#     t0, _ = _day_bounds(days[0])
#     _, t1 = _day_bounds(days[-1])
 
#     # Lấy dữ liệu 1 lần
#     checkins_map = _bulk_fetch_checkins(emps, t0, t1)     # SỬ DỤNG t0,t1 (datetime)
#     leaves_set   = _bulk_fetch_leaves(emps, t0, t1)
 
#     out = []
#     for d in days:
#         for emp in emps:
#             if (emp['name'], d) in leaves_set:
#                 continue
#             rec = checkins_map.get((emp['name'], d), {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})
#             fi, lo = rec["first_in"], rec["last_out"]
#             ci, co = rec["cnt_in"],  rec["cnt_out"]
 
#             status = "OK"
#             issues = []
 
#             if ci == 0 and co == 0:
#                 status = "Đã tạo đơn chờ duyệt" if (emp['name'], d) in leaves_set else "Vắng mặt"
#             elif ci > 0 and co == 0:
#                 if fi and fi.time() > SHIFT_START:
#                     issues.append("Đi muộn")
#                 issues.append("Quên chấm công")
#             elif co > 0 and ci == 0:
#                 issues.append("Quên chấm công")
#                 if lo and lo.time() < SHIFT_END:
#                     issues.append("Về sớm")
#             else:
#                 if fi and fi.time() > SHIFT_START:
#                     issues.append("Đi muộn")
#                 if lo and lo.time() < SHIFT_END:
#                     issues.append("Về sớm")
 
#             if issues:
#                 status = ", ".join(issues)
 
#             if status != "OK":
#                 approver_user = _employee_user_id(emp.get('reports_to')) if emp.get('reports_to') else None
#                 out.append({
#                     "employee": emp['name'],
#                     "employee_name": emp['employee_name'],
#                     "department": emp['department'],
#                     "user_id": emp.get('user_id'),
#                     "date": d.isoformat(),
#                     "approver": approver_user,
#                     "from_date": from_date.isoformat(),
#                     "to_date": to_date.isoformat(),
#                     "first_in": fi.strftime("%H:%M:%S") if fi else None,
#                     "last_out": lo.strftime("%H:%M:%S") if lo else None,
#                     "status": status,
#                 })
#     return out

# def _close_todos_for_doc(doc: Document):
#     names = frappe.get_all(
#         "ToDo",
#         filters={
#             "reference_type": doc.doctype,
#             "reference_name": doc.name,
#             "status": ["!=", "Cancelled"],
#         },
#         pluck="name",
#     )
#     for n in names:
#         frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


# def _delete_todos_for_doc(doc: Document):
#     names = frappe.get_all(
#         "ToDo",
#         filters={
#             "reference_type": doc.doctype,
#             "reference_name": doc.name,
#         },
#         pluck="name",
#     )
#     for n in names:
#         try:
#             frappe.delete_doc("ToDo", n, ignore_permissions=True, force=1)
#         except Exception:
#             frappe.log_error(frappe.get_traceback(), f"Không xoá được ToDo: {n}")

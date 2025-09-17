from __future__ import unicode_literals

import frappe
from frappe import _
from hrms.hr.doctype.attendance.attendance import (
	Attendance
)
from datetime import datetime, date, time, timedelta
from frappe.utils import getdate, now_datetime


class VntAttendance(Attendance):
	pass


@frappe.whitelist()
def create_attendance_from_checkin():
	"""
	Loop qua tất cả employee active và tạo Attendance từ đầu tháng đến ngày hiện tại (hoặc end_date).
	- end_date: Ngày kết thúc (YYYY-MM-DD), nếu None thì lấy ngày hiện tại.
	- Logic:
	  - Lấy danh sách employee active.
	  - Loop qua từng ngày từ đầu tháng đến end_date.
	  - Gọi get_employee_checkin để lấy in_time, out_time.
	  - Tạo Attendance nếu có cả in_time và out_time, và chưa tồn tại Attendance.
	"""
	# lấy ngày hiện tại
	date = now_datetime().date()
	start_date = date.replace(day=1)  # Đầu tháng
	# Lấy danh sách employee active
	employees = frappe.get_all('Employee', filters={'status': 'Active'}, fields=['name', 'employee_name', 'company', 'department'])
	if not employees:
		frappe.msgprint("Không tìm thấy employee active nào!")
		return
	
	# Loop qua từng ngày từ đầu tháng đến end_date
	for emp in employees:
		# Lấy thời gian check-in/check-out
		leave_apps = frappe.get_all('Leave Application', 
			filters={
				'employee': emp['name'],
				'docstatus': 1,  # Chỉ lấy các đơn đã được duyệt
				'from_date': ['<=', date],
				'to_date': ['>=', start_date]
			},
			fields=['from_date', 'to_date']
		)
		current_date = start_date
		while current_date <= date:
			# Kiểm tra xem ngày hiện tại có nằm trong Leave Application không
			is_leave_day = False
			for leave in leave_apps:
				leave_from = getdate(leave['from_date'])
				leave_to = getdate(leave['to_date'])
				if leave_from <= current_date <= leave_to:
					is_leave_day = True
					break
			if is_leave_day:
				# Bỏ qua ngày này nếu nhân viên đang trong kỳ nghỉ phép
				current_date += timedelta(days=1)
				continue
			# Check exists Attendance
			existing_att = frappe.db.exists('Attendance', {
				'employee': emp['name'],
				'attendance_date': current_date,
				'docstatus': 1
			})
			if existing_att:
				frappe.throw(f"Employee {emp['name']} ngày {current_date}: Attendance đã tồn tại")
				current_date += timedelta(days=1)
				continue
			in_time, out_time = _get_employee_checkin(emp['name'], current_date)
			
			# Nếu không có cả IN và OUT, skip employee này cho ngày hiện tại
			# check thêm các trường hợp leave application ở đây
			if not (in_time and out_time):
				# frappe.throw(f"Employee {emp['name']} ngày {current_date}: Thiếu check-in hoặc check-out")
				current_date += timedelta(days=1)
				continue
	
			# Tạo Attendance
			att = frappe.new_doc('Attendance')
			att.employee = emp['name']
			att.employee_name = emp['employee_name']
			att.company = emp['company']
			att.attendance_date = current_date
			att.status = 'Present'  # Có thể điều chỉnh logic status
			att.shift = 'Hành chính'  # Nếu có field shift
			att.docstatus = 1  # Submit luôn
			att.save()
			current_date += timedelta(days=1)
	return

def _get_employee_checkin(employee, date=None):
	"""
	Tạo Attendance từ Employee Checkin.
	- employee: Tên employee (string).
	- date: Ngày (YYYY-MM-DD), nếu None thì lấy ngày hôm nay.
	
	Logic:
	- Lấy MIN(time) cho log_type='IN' trong ngày.
	- Lấy MAX(time) cho log_type='OUT' trong ngày.
	- Nếu có IN (và OUT tùy chọn), tạo Attendance với status='Present'.
	- Tránh duplicate bằng cách check nếu Attendance đã tồn tại cho employee/date.
	"""
	if not date:
		date = now_datetime().date()
	else:
		date = getdate(date)
	
	start_date = datetime.combine(date, datetime.min.time())
	end_date = datetime.combine(date, datetime.max.time())
	
	# Query MIN IN time
	in_time = frappe.db.sql("""
		SELECT MIN(time) as min_time
		FROM `tabEmployee Checkin`
		WHERE employee = %s
		AND log_type = 'IN'
		AND time >= %s
		AND time <= %s
	""", (employee, start_date, end_date), as_dict=1)
	
	in_time = in_time[0]['min_time'] if in_time and in_time[0]['min_time'] else None
	
	# Query MAX OUT time
	out_time = frappe.db.sql("""
		SELECT MAX(time) as max_time
		FROM `tabEmployee Checkin`
		WHERE employee = %s
		AND log_type = 'OUT'
		AND time >= %s
		AND time <= %s
	""", (employee, start_date, end_date), as_dict=1)
	
	out_time = out_time[0]['max_time'] if out_time and out_time[0]['max_time'] else None
	return in_time, out_time

# @frappe.whitelist()
# def build_attendance_from_checkins(date_from=None, date_to=None, update_existing=False):
#     """
#     Tạo Attendance từ Employee Checkin:
#       - Với mỗi (employee, attendance_date):
#         * IN = time nhỏ nhất (log_type='IN')
#         * OUT = time lớn nhất (log_type='OUT')
#       - Status:
#         * Có cả IN & OUT -> Present, tính working_hours
#         * Chỉ có 1 đầu -> Half Day
#       - Nếu đã có Attendance:
#         * update nếu update_existing=True
#         * ngược lại thì bỏ qua
#     Params:
#       - date_from, date_to: 'YYYY-MM-DD' (mặc định = hôm nay)
#       - update_existing: bool
#     Return: dict summary
#     """
#     # ---- resolve ngày ----
#     if not date_from and not date_to:
#         date_from = date_to = cstr(getdate())  # hôm nay
#     elif date_from and not date_to:
#         date_to = date_from
#     elif date_to and not date_from:
#         date_from = date_to

#     d_from = getdate(date_from)
#     d_to   = getdate(date_to)
#     if d_from > d_to:
#         frappe.throw(_("date_from must be <= date_to"))

#     # ---- lấy tất cả checkins trong khoảng ngày ----
#     # dùng where theo khoảng [00:00:00, 23:59:59] của từng ngày
#     # để tránh lệ thuộc timezone DB, ta lấy min-max python theo ngày
#     d_today = getdate(today())                 # ngày hôm nay (date)
#     d_month_start = d_today.replace(day=1)
#     start_dt = datetime.combine(d_month_start, time.min)  # 00:00:00 ngày 01
#     end_dt   = datetime.combine(d_today, time.max)
#     # start_dt = datetime.combine(d_from, time.min)
#     # end_dt   = datetime.combine(d_to,   time.max)

#     rows = frappe.get_all(
#         "Employee Checkin",
#         filters={"time": ["between", [start_dt, end_dt]]},
#         fields=["name", "employee", "log_type", "time"],
#         order_by="employee asc, time asc",
#         limit_page_length=0,
#     )
	

#     # ---- gom nhóm theo (employee, date) rồi tìm IN min & OUT max ----
#     groups = {}  # key: (employee, yyyy-mm-dd) -> {"in": dt|None, "out": dt|None, "checkins": [names]}
#     for r in rows:
#         emp = r["employee"]
#         t: datetime = r["time"]
#         day_key = t.date().isoformat()
#         key = (emp, day_key)

#         g = groups.setdefault(key, {"in": None, "out": None, "checkin_names": []})
#         g["checkin_names"].append(r["name"])

#         if r["log_type"] == "IN":
#             # lấy nhỏ nhất
#             g["in"] = t if (g["in"] is None or t < g["in"]) else g["in"]
#         elif r["log_type"] == "OUT":
#             # lấy lớn nhất
#             g["out"] = t if (g["out"] is None or t > g["out"]) else g["out"]

#     created, updated, skipped = 0, 0, 0
#     details = []
#     frappe.throw(f"{groups}")
#     for (emp, day_str), val in groups.items():
#         att_date = getdate(day_str)
#         in_time  = val["in"]
#         out_time = val["out"]

#         # Không có bất kỳ IN/OUT nào thì bỏ
#         if not in_time and not out_time:
#             skipped += 1
#             continue

#         status = "Present" if (in_time and out_time) else "Half Day"

#         # đã có Attendance cho (employee, date)?
#         att_name = frappe.db.get_value(
#             "Attendance",
#             {"employee": emp, "attendance_date": att_date},
#             "name",
#         )

#         # Nếu có rồi mà không cho update -> skip
#         if att_name and not update_existing:
#             skipped += 1
#             details.append(f"Skip {emp} {day_str}: exists {att_name}")
#             continue

#         # Chuẩn bị fields chung
#         doc_fields = {
#             "doctype": "Attendance",
#             "employee": emp,
#             "attendance_date": att_date,
#             "status": status,
#         }

#         # nếu hệ thống bạn có field in_time/out_time (HRMS v15 thường có)
#         if "in_time" in frappe.get_meta("Attendance").get_fieldnames():
#             doc_fields["in_time"] = in_time
#         if "out_time" in frappe.get_meta("Attendance").get_fieldnames():
#             doc_fields["out_time"] = out_time

#         # working_hours nếu có đủ hai đầu
#         if in_time and out_time and "working_hours" in frappe.get_meta("Attendance").get_fieldnames():
#             wh = (out_time - in_time).total_seconds() / 3600.0
#             # tránh số âm (trường hợp lệch ngày)
#             if wh < 0:
#                 wh = 0
#             doc_fields["working_hours"] = round(wh, 3)

#         if att_name:
#             # update
#             att = frappe.get_doc("Attendance", att_name)
#             att.update(doc_fields)
#             att.save(ignore_permissions=True)
#             updated += 1
#             details.append(f"Update {emp} {day_str}: {att.name}")
#         else:
#             # create
#             att = frappe.get_doc(doc_fields)
#             att.insert(ignore_permissions=True)
#             created += 1
#             details.append(f"Create {emp} {day_str}: {att.name}")

#         # (Tùy chọn) nếu bạn có custom link 'attendance' trong Employee Checkin thì gắn link
#         # không có thì thôi, tránh lỗi bằng try/ignore
#         try:
#             if frappe.db.has_column("Employee Checkin", "attendance"):
#                 frappe.db.sql(
#                     """
#                     UPDATE `tabEmployee Checkin`
#                     SET attendance = %s
#                     WHERE name IN %(names)s
#                     """,
#                     (att.name, tuple(val["checkin_names"]) or ("",)),
#                 )
#         except Exception:
#             frappe.db.rollback()  # không để ảnh hưởng tới Attendance
#         finally:
#             frappe.db.commit()

#     return {
#         "date_from": cstr(d_from),
#         "date_to": cstr(d_to),
#         "created": created,
#         "updated": updated,
#         "skipped": skipped,
#         "rows": len(rows),
#         "notes": details[:50],  
#     }
# # Copyright (c) 2025, vinatex and contributors
# # For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime, time, date, timedelta
import calendar
from frappe.utils import getdate
# from hrms.hr.utils import get_holiday_list_for_employee(employee)


class VNTAttendanceConfirm(Document):
	pass


@frappe.whitelist()
def make_attendance_confirm():
    data = check_employee_checkin_by_days()
    data_sorted = sorted(data, key=lambda r: (r.get("employee") or ""))
    grouped_data = {}
    for entry in data_sorted:
        employee_id = entry['employee']
        if employee_id not in grouped_data:
            grouped_data[employee_id] = {
                'employee': entry['employee'],
                'employee_name': entry['employee_name'],
                'department': entry['department'],
                'email': entry['user_id'],
                'from_date': entry['from_date'],
                'to_date': entry['to_date'],
                'approver': entry['approver'],
                'records': []
            }
        grouped_data[employee_id]['records'].append({
            'date': entry['date'],
            'first_in': entry['first_in'] if entry['first_in'] else None,
            'last_out': entry['last_out'] if entry['last_out'] else None,
            'status': entry['status']
        })
    # Convert to list for output
    result = list(grouped_data.values())
    for i in result:
        att = frappe.new_doc("VNT Attendance Confirm")
        att.employee = i.get("employee")
        att.employee_name = i.get("employee_name")
        att.department = i.get("department")
        att.email = i.get("email")
        att.from_date = i.get("from_date")
        att.to_date = i.get("to_date")
        att.approver = i.get('approver')
        for r in i.get("records"):
            att.append("items", {
                "date": r.get("date"),
                "time_in": r.get("first_in") if r.get("first_in") else None,
                "time_out": r.get("last_out") if r.get("last_out") else None,
                "status": r.get("status"),
            })
        att.insert()
        # att.submit()  


@frappe.whitelist()
def get_working_dates_of_month():
    # lấy ra các ngày làm việc trong tháng hiện tại (đã loại bỏ holiday)
    today = date.today()
    year = today.year
    month = today.month
    company = frappe.defaults.get_user_default("Company")
    if company:
        holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
        if not holiday_list:
            frappe.throw("Không xác định được Holiday List (thiếu employee/company/holiday_list).")

    # 2) Tính khoảng đầu-cuối tháng
    start_date = date(year, month, 1)
    end_date   = end_date = datetime.now().date()

    if end_date < start_date:
        return []

    # 3) Lấy toàn bộ holiday trong tháng bằng MỘT query, rồi cho vào set để tra nhanh
    holidays = frappe.get_all(
        "Holiday",
        filters={
            "parent": holiday_list,
            "holiday_date": ["between", [start_date, end_date]],
        },
        pluck="holiday_date",  # trả về list các date
    )
    holiday_set = set(holidays)  # O(1) lookup

    # 4) Sinh tất cả ngày trong tháng và lọc ra ngày làm việc
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
    if employees:
        return
    # Lấy toàn bộ nhân viên Active
    return frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name", "department", 'user_id', 'leave_approver'])


def _bulk_fetch_checkins(employees, d_start, d_end):
    """Trả về dict[(emp, date)] = {'first_in': dt|None, 'last_out': dt|None, 'cnt_in': int, 'cnt_out': int}"""
    if not employees:
        return {}

    rows = frappe.db.sql(
        """
        SELECT employee, log_type, time
        FROM `tabEmployee Checkin`
        WHERE employee IN %(emps)s
          AND time BETWEEN %(t0)s AND %(t1)s
        """,
        {"emps": ('VGT00047', 'VGT00050'), "t0": d_start, "t1": d_end},
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

def _bulk_fetch_leaves(employees, d_start, d_end):
    """Trả về set[(emp, date)] cho các ngày có Leave Application (không quan tâm trạng thái, theo yêu cầu)."""
    if not employees:
        return set()

    leaves = frappe.db.sql(
        """
        SELECT employee, from_date, to_date
        FROM `tabLeave Application`
        WHERE employee IN %(emps)s
          AND to_date   >= %(d0)s
          AND from_date <= %(d1)s
          AND status NOT IN ('Rejected','Cancelled')
        """,
        {"emps": tuple(employees), "d0": d_start.date(), "d1": d_end.date()},
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

@frappe.whitelist()
def check_employee_checkin_by_days(employees=None):
    """
    working_days: list[str 'YYYY-MM-DD'] - các ngày làm việc trong tháng (đã lọc holiday ở ngoài nếu muốn)
    employees: list[str] hoặc None -> mặc định tất cả Employee Active
    shift_start / shift_end: 'HH:MM', mặc định '08:15' và '17:00'

    Return: list[ {employee, date, first_in, last_out, status} ]
    """
    # Chuẩn hoá input
    working_days = get_working_dates_of_month()
    from_date, to_date = min_max_date(working_days)
    days = _parse_dates(working_days)
    if not days:
        return []

    emps = _pick_employees(employees)
    # Giờ chuẩn ca
    shift_start="08:15"
    shift_end="17:00"
    h1, m1 = map(int, shift_start.split(":"))
    h2, m2 = map(int, shift_end.split(":"))
    SHIFT_START = time(h1, m1)
    SHIFT_END   = time(h2, m2)

    # Khoảng thời gian lớn nhất để bulk-fetch
    t0, _ = _day_bounds(days[0])
    _, t1 = _day_bounds(days[-1])

    # Lấy dữ liệu 1 lần
    checkins_map = _bulk_fetch_checkins(emps, from_date, to_date)
    leaves_set   = _bulk_fetch_leaves(emps, t0, t1)
    # frappe.throw(f"{checkins_map}")
    out = []
    for d in days:
        for emp in emps:
            rec = checkins_map.get((emp['name'], d), {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})
            fi, lo = rec["first_in"], rec["last_out"]
            ci, co = rec["cnt_in"],  rec["cnt_out"]

            status = "OK"
            issues = []  # gom các lỗi theo thứ tự yêu cầu

            # Case 3: không có checkin -> kiểm tra Leave Application
            if ci == 0 and co == 0:
                status = "Đã tạo đơn chờ duyệt" if (emp['name'], d) in leaves_set else "Vắng mặt"

            # Case 2 (một chiều) + combo logic
            elif ci > 0 and co == 0:
                # Nếu đi muộn buổi sáng và quên OUT -> "Đi muộn, Quên chấm công"
                if fi and fi.time() > SHIFT_START:
                    issues.append("Đi muộn")
                issues.append("Quên chấm công")

            elif co > 0 and ci == 0:
                # Nếu quên IN và về sớm -> "Quên chấm công, Về sớm"
                issues.append("Quên chấm công")
                if lo and lo.time() < SHIFT_END:
                    issues.append("Về sớm")

            # Case 1: có đủ IN/OUT -> xét đi muộn / về sớm
            else:
                if fi and fi.time() > SHIFT_START:
                    issues.append("Đi muộn")
                if lo and lo.time() < SHIFT_END:
                    issues.append("Về sớm")

            if issues:
                status = " , ".join(issues)

            # chỉ trả về nếu status != "OK"
            if status != "OK":
                out.append({
                    "employee": emp['name'],
                    "employee_name": emp['employee_name'],
                    "department": emp['department'],
                    "user_id": emp.get('user_id'),
                    "date": d.isoformat(),
                    "approver": emp.get('leave_approver'),
                    "from_date": from_date.isoformat(),
                    "to_date": to_date.isoformat(),
                    "first_in": fi.strftime("%H:%M:%S") if fi else None,
                    "last_out": lo.strftime("%H:%M:%S") if lo else None,
                    "status": status,
                })
    return out


def min_max_date(dates):
    # lọc None nếu có
    dates = [d for d in dates if d]
    if not dates:
        return None, None
    return min(dates), max(dates)



# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document
# from datetime import datetime, time, date, timedelta
# import calendar
# from frappe.utils import getdate
# # from hrms.hr.utils import get_holiday_list_for_employee(employee)


# class VNTAttendanceConfirm(Document):
# 	pass


# @frappe.whitelist()
# def make_attendance_confirm():
#     data = check_employee_checkin_by_days()
#     data_sorted = sorted(data, key=lambda r: (r.get("employee") or ""))
#     frappe.throw(F"{data_sorted}")    


# @frappe.whitelist()
# def get_working_dates_of_month():
#     # lấy ra các ngày làm việc trong tháng hiện tại (đã loại bỏ holiday)
#     today = date.today()
#     year = today.year
#     month = today.month
#     company = frappe.defaults.get_user_default("Company")
#     if company:
#         holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
#         if not holiday_list:
#             frappe.throw("Không xác định được Holiday List (thiếu employee/company/holiday_list).")

#     # 2) Tính khoảng đầu-cuối tháng
#     start_date = date(year, month, 1)
#     end_date   = date(year, month, calendar.monthrange(year, month)[1])

#     if end_date < start_date:
#         return []

#     # 3) Lấy toàn bộ holiday trong tháng bằng MỘT query, rồi cho vào set để tra nhanh
#     holidays = frappe.get_all(
#         "Holiday",
#         filters={
#             "parent": holiday_list,
#             "holiday_date": ["between", [start_date, end_date]],
#         },
#         pluck="holiday_date",  # trả về list các date
#     )
#     holiday_set = set(holidays)  # O(1) lookup

#     # 4) Sinh tất cả ngày trong tháng và lọc ra ngày làm việc
#     days = (end_date - start_date).days + 1
#     working_dates = [
#         (start_date + timedelta(days=i))
#         for i in range(days)
#         if (start_date + timedelta(days=i)) not in holiday_set
#     ]
#     return working_dates
	

# def _day_bounds(d):
#     return datetime.combine(d, time.min), datetime.combine(d, time.max)

# def _parse_dates(dates):
#     """dates: list[str 'YYYY-MM-DD'] -> list[date]; bỏ trùng & sort"""
#     ds = sorted({getdate(x) for x in dates})
#     return ds

# def _pick_employees(employees):
#     if employees:
#         return
#     # Lấy toàn bộ nhân viên Active
#     return frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name", "department", 'user_id'])

# def _bulk_fetch_checkins(employees, d_start, d_end):
#     """Trả về dict[(emp, date)] = {'first_in': dt|None, 'last_out': dt|None, 'cnt_in': int, 'cnt_out': int}"""
#     if not employees:
#         return {}

#     rows = frappe.db.sql(
#         """
#         SELECT employee, log_type, time
#         FROM `tabEmployee Checkin`
#         WHERE employee IN %(emps)s
#           AND time BETWEEN %(t0)s AND %(t1)s
#         """,
#         {"emps": tuple(employees), "t0": d_start, "t1": d_end},
#         as_dict=True,
#     )

#     box = {}
#     for r in rows:
#         emp = r["employee"]
#         d   = getdate(r["time"])
#         key = (emp, d)
#         item = box.setdefault(key, {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})

#         if r["log_type"] == "IN":
#             item["cnt_in"] += 1
#             if item["first_in"] is None or r["time"] < item["first_in"]:
#                 item["first_in"] = r["time"]
#         elif r["log_type"] == "OUT":
#             item["cnt_out"] += 1
#             if item["last_out"] is None or r["time"] > item["last_out"]:
#                 item["last_out"] = r["time"]

#     return box

# def _bulk_fetch_leaves(employees, d_start, d_end):
#     """Trả về set[(emp, date)] cho các ngày có Leave Application (không quan tâm trạng thái, theo yêu cầu)."""
#     if not employees:
#         return set()

#     leaves = frappe.db.sql(
#         """
#         SELECT employee, from_date, to_date
#         FROM `tabLeave Application`
#         WHERE employee IN %(emps)s
#           AND to_date   >= %(d0)s
#           AND from_date <= %(d1)s
#           AND status NOT IN ('Rejected','Cancelled')
#         """,
#         {"emps": tuple(employees), "d0": d_start.date(), "d1": d_end.date()},
#         as_dict=True,
#     )

#     covered = set()
#     for r in leaves:
#         emp = r["employee"]
#         d0  = getdate(r["from_date"])
#         d1  = getdate(r["to_date"])
#         cur = d0
#         while cur <= d1:
#             if d_start.date() <= cur <= d_end.date():
#                 covered.add((emp, cur))
#             cur += timedelta(days=1)
#     return covered

# @frappe.whitelist()
# def check_employee_checkin_by_days(employees=None):
#     """
#     working_days: list[str 'YYYY-MM-DD'] - các ngày làm việc trong tháng (đã lọc holiday ở ngoài nếu muốn)
#     employees: list[str] hoặc None -> mặc định tất cả Employee Active
#     shift_start / shift_end: 'HH:MM', mặc định '08:15' và '17:00'

#     Return: list[ {employee, date, first_in, last_out, status} ]
#     """
#     # Chuẩn hoá input
#     working_days = get_working_dates_of_month()
#     days = _parse_dates(working_days)
#     if not days:
#         return []

#     emps = _pick_employees(employees)

#     # Giờ chuẩn ca
#     shift_start="08:15"
#     shift_end="17:00"
#     h1, m1 = map(int, shift_start.split(":"))
#     h2, m2 = map(int, shift_end.split(":"))
#     SHIFT_START = time(h1, m1)
#     SHIFT_END   = time(h2, m2)

#     # Khoảng thời gian lớn nhất để bulk-fetch
#     t0, _ = _day_bounds(days[0])
#     _, t1 = _day_bounds(days[-1])

#     # Lấy dữ liệu 1 lần
#     checkins_map = _bulk_fetch_checkins(emps, t0, t1)
#     leaves_set   = _bulk_fetch_leaves(emps, t0, t1)

#     out = []
#     for d in days:
#         for emp in emps:
#             rec = checkins_map.get((emp['name'], d), {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})
#             fi, lo = rec["first_in"], rec["last_out"]
#             ci, co = rec["cnt_in"],  rec["cnt_out"]

#             status = "OK"
#             issues = []  # gom các lỗi theo thứ tự yêu cầu

#             # Case 3: không có checkin -> kiểm tra Leave Application
#             if ci == 0 and co == 0:
#                 status = "Đã tạo đơn chờ duyệt" if (emp['name'], d) in leaves_set else "Vắng mặt"

#             # Case 2 (một chiều) + combo logic
#             elif ci > 0 and co == 0:
#                 # Nếu đi muộn buổi sáng và quên OUT -> "Đi muộn, Quên chấm công"
#                 if fi and fi.time() > SHIFT_START:
#                     issues.append("Đi muộn")
#                 issues.append("Quên chấm công")

#             elif co > 0 and ci == 0:
#                 # Nếu quên IN và về sớm -> "Quên chấm công, Về sớm"
#                 issues.append("Quên chấm công")
#                 if lo and lo.time() < SHIFT_END:
#                     issues.append("Về sớm")

#             # Case 1: có đủ IN/OUT -> xét đi muộn / về sớm
#             else:
#                 if fi and fi.time() > SHIFT_START:
#                     issues.append("Đi muộn")
#                 if lo and lo.time() < SHIFT_END:
#                     issues.append("Về sớm")

#             if issues:
#                 status = " , ".join(issues)

#             # chỉ trả về nếu status != "OK"
#             if status != "OK":
#                 out.append({
#                     "employee": emp['name'],
#                     "employee_name": emp['employee_name'],
#                     "department": emp['department'],
#                     "user_id": emp.get('user_id'),
#                     "date": d.isoformat(),
#                     "first_in": fi.strftime("%H:%M:%S") if fi else None,
#                     "last_out": lo.strftime("%H:%M:%S") if lo else None,
#                     "status": status,
#                 })

#     return out

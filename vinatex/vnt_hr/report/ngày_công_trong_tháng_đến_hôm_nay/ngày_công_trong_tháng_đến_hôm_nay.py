# -*- coding: utf-8 -*-
import json
from datetime import datetime, time, timedelta

import frappe
from frappe.utils import cint, get_first_day, get_last_day, getdate, today

STATUS_CODE = {
    "CHƯA VÀO LÀM": "CV",
    "NGHỈ LỄ": "L",
    "CUỐI TUẦN": "T",
    "ĐI LÀM": "X",
    "VẮNG MẶT": "V",
    "QUÊN CHẤM CÔNG": "O",
    "NGHỈ PHÉP": "P",
    "NGHỈ VIỆC RIÊNG KHÔNG HƯỞNG LƯƠNG": "Ro",
    "NGHỈ CÓ HƯỞNG LƯƠNG, CHẾ ĐỘ": "CĐ",
    "NGHỈ HƯỞNG CHẾ ĐỘ BHXH": "BH",
    "VẮNG MẶT TẠI TRỤ SỞ CÔNG TY CÓ LÝ DO CÔNG VIỆC": "CT",
    "NGHỈ NỬA NGÀY": "N1/2",
}

LEAVE_TYPE_CODE = {
    "Unpaid Leave": STATUS_CODE["NGHỈ VIỆC RIÊNG KHÔNG HƯỞNG LƯƠNG"],
    "Leave Without Pay": STATUS_CODE["NGHỈ VIỆC RIÊNG KHÔNG HƯỞNG LƯƠNG"],
    "Sick Leave": STATUS_CODE["NGHỈ HƯỞNG CHẾ ĐỘ BHXH"],
    "Maternity Leave": STATUS_CODE["NGHỈ CÓ HƯỞNG LƯƠNG, CHẾ ĐỘ"],
}

TOTAL_FIELD_FOR_CODE = {
    STATUS_CODE["ĐI LÀM"]: "tot_present",
    STATUS_CODE["NGHỈ PHÉP"]: "tot_leave",
    STATUS_CODE["NGHỈ LỄ"]: "tot_holiday",
    STATUS_CODE["CUỐI TUẦN"]: "tot_weekend",
    STATUS_CODE["VẮNG MẶT"]: "tot_absent",
    STATUS_CODE["QUÊN CHẤM CÔNG"]: "tot_miss",
    STATUS_CODE["CHƯA VÀO LÀM"]: "tot_not_joined",
    STATUS_CODE["VẮNG MẶT TẠI TRỤ SỞ CÔNG TY CÓ LÝ DO CÔNG VIỆC"]: "tot_on_duty",
    STATUS_CODE["NGHỈ VIỆC RIÊNG KHÔNG HƯỞNG LƯƠNG"]: "tot_unpaid_leave",
    STATUS_CODE["NGHỈ CÓ HƯỞNG LƯƠNG, CHẾ ĐỘ"]: "tot_paid_leave",
    STATUS_CODE["NGHỈ HƯỞNG CHẾ ĐỘ BHXH"]: "tot_social_leave",
    STATUS_CODE["NGHỈ NỬA NGÀY"]: "tot_half_day",
}

def execute(filters=None):
    """
    Trả về tổng NGÀY CÔNG trong tháng (đến HÔM NAY):
      - Present = 1
      - Half Day = 0.5
      - Work From Home = 1 (nếu bật count_wfh)
    Ưu tiên dùng from_date/to_date nếu truyền vào; end_date luôn cắt <= hôm nay.
    Nếu không truyền employee, tự map từ frappe.session.user -> Employee(Active).
    """

    # Parse filters an toàn
    if isinstance(filters, str):
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            try:
                filters = json.loads(filters)
            except Exception:
                filters = {}
    filters = filters or {}

    # Map user -> employee (dùng RAW SQL để không dính ignore_permissions)
    employee = filters.get("employee")
    if not employee:
        row = frappe.db.sql(
            """SELECT name FROM `tabEmployee`
               WHERE user_id=%s AND status='Active' LIMIT 1""",
            (frappe.session.user,),
        )
        employee = row[0][0] if row else None
    if not employee:
        return _columns(), [{"value": 0.0}], None

    # Khoảng tính: ưu tiên from_date/to_date; luôn cắt end_date đến HÔM NAY
    ref_date = getdate(today())
    if filters.get("from_date"):
        start_date = getdate(filters["from_date"])
        end_date = getdate(filters.get("to_date") or ref_date)
    else:
        month = cint(filters.get("month") or 0)
        year  = cint(filters.get("year")  or 0)
        if month and year:
            start_date = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
        else:
            start_date = get_first_day(ref_date)
        end_date = get_last_day(start_date)
    # CHỈ lấy đến hôm nay
    end_date = min(end_date, ref_date)
    if end_date < start_date:
        return _columns(), [{"value": 0.0}], None

    # Tính WFH như Present hay không
    count_wfh = cint(filters.get("count_wfh") or 0)
    wfh_sql = " OR a.status = 'Work From Home'" if count_wfh else ""

    # Tổng ngày công
    sql = f"""
        SELECT COALESCE(SUM(
            CASE
                WHEN (a.status = 'Present' {wfh_sql}) THEN 1
                WHEN a.status = 'Half Day' THEN 0.5
                ELSE 0
            END
        ), 0) AS days
        FROM `tabAttendance` a
        WHERE a.employee = %(employee)s
          AND a.attendance_date BETWEEN %(from)s AND %(to)s
          AND a.docstatus = 1
    """
    total_days = (
        frappe.db.sql(
            sql, {"employee": employee, "from": start_date, "to": end_date}, as_dict=True
        )[0].days
        or 0.0
    )

    emp_doc = _get_employee_doc(employee)
    if not emp_doc:
        return _columns(), [{"value": float(total_days)}], None

    company = (
        filters.get("company")
        or emp_doc.get("company")
        or frappe.defaults.get_user_default("Company")
        or frappe.defaults.get_global_default("company")
    )

    days = list(_daterange(start_date, end_date))
    base_columns = _columns()
    info_columns = [
        {
            "label": "Mã NV",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 110,
        },
        {
            "label": "Tên nhân viên",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": "Phòng ban",
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 160,
        },
        {
            "label": "Công ty",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 160,
        },
    ]
    day_columns = [
        {
            "label": f"{d.day:02d}",
            "fieldname": f"d{d.day:02d}",
            "fieldtype": "Data",
            "width": 50,
        }
        for d in days
    ]
    summary_columns = [
        {"fieldname": "tot_present", "label": "Đi làm", "fieldtype": "Int", "width": 80},
        {"fieldname": "tot_leave", "label": "Nghỉ phép", "fieldtype": "Int", "width": 90},
        {"fieldname": "tot_holiday", "label": "Nghỉ lễ", "fieldtype": "Int", "width": 80},
        {"fieldname": "tot_weekend", "label": "Cuối tuần", "fieldtype": "Int", "width": 90},
        {"fieldname": "tot_absent", "label": "Vắng", "fieldtype": "Int", "width": 70},
        {"fieldname": "tot_miss", "label": "Quên CC", "fieldtype": "Int", "width": 80},
        {"fieldname": "tot_on_duty", "label": "Công tác", "fieldtype": "Int", "width": 90},
        {"fieldname": "tot_unpaid_leave", "label": "Nghỉ K/L", "fieldtype": "Int", "width": 80},
        {"fieldname": "tot_paid_leave", "label": "Nghỉ hưởng lương", "fieldtype": "Int", "width": 130},
        {"fieldname": "tot_social_leave", "label": "Nghỉ BHXH", "fieldtype": "Int", "width": 95},
        {"fieldname": "tot_half_day", "label": "Nửa ngày", "fieldtype": "Int", "width": 90},
        {"fieldname": "tot_not_joined", "label": "Chưa vào làm", "fieldtype": "Int", "width": 110},
    ]

    columns = base_columns + info_columns + day_columns + summary_columns

    holiday_days = _holiday_days(emp_doc, company, start_date, end_date)
    attendance_map = _attendance_map(employee, start_date, end_date)
    leave_map = _leave_map(employee, start_date, end_date)
    checkin_map = _checkin_map(employee, start_date, end_date)

    totals = {col["fieldname"]: 0 for col in summary_columns}
    row = {
        "value": float(total_days),
        "employee": employee,
        "employee_name": emp_doc.get("employee_name") or employee,
        "department": emp_doc.get("department"),
        "company": company,
    }

    for d in days:
        code = _status_code_for_day(
            d,
            emp_doc,
            holiday_days,
            attendance_map,
            leave_map,
            checkin_map,
        )
        fieldname = f"d{d.day:02d}"
        row[fieldname] = code

        total_key = TOTAL_FIELD_FOR_CODE.get(code)
        if total_key and total_key in totals:
            totals[total_key] += 1

    row.update(totals)

    return columns, [row], None


def _columns():
    # Number Card sẽ lấy cột đầu tiên 'value'
    return [{
        "label": "Tổng số ngày công đã đi làm trong tháng",
        "fieldname": "value",
        "fieldtype": "Float",
        "width": 150,
    }]


def _get_employee_doc(employee):
    return frappe.db.get_value(
        "Employee",
        employee,
        [
            "name",
            "employee_name",
            "department",
            "company",
            "date_of_joining",
            "relieving_date",
            "holiday_list",
        ],
        as_dict=True,
    )


def _daterange(start_date, end_date):
    cur = start_date
    while cur <= end_date:
        yield cur
        cur += timedelta(days=1)


def _holiday_days(emp_doc, company, start_date, end_date):
    holiday_list = emp_doc.get("holiday_list")
    if not holiday_list and company:
        holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
    if not holiday_list:
        return set()

    rows = frappe.db.sql(
        """
        SELECT holiday_date, COALESCE(weekly_off, 0) AS weekly_off
        FROM `tabHoliday`
        WHERE parent=%(holiday_list)s
          AND holiday_date BETWEEN %(start)s AND %(end)s
    """,
        {"holiday_list": holiday_list, "start": start_date, "end": end_date},
        as_dict=True,
    )
    return {
        getdate(r.holiday_date)
        for r in rows
        if cint(r.weekly_off) == 0
    }


def _attendance_map(employee, start_date, end_date):
    rows = frappe.db.sql(
        """
        SELECT attendance_date, status, leave_type
        FROM `tabAttendance`
        WHERE docstatus = 1
          AND employee = %(employee)s
          AND attendance_date BETWEEN %(start)s AND %(end)s
    """,
        {"employee": employee, "start": start_date, "end": end_date},
        as_dict=True,
    )
    return {
        getdate(r.attendance_date): {"status": r.status, "leave_type": r.leave_type}
        for r in rows
    }


def _leave_map(employee, start_date, end_date):
    rows = frappe.db.sql(
        """
        SELECT from_date, to_date, half_day, half_day_date, leave_type
        FROM `tabLeave Application`
        WHERE docstatus = 1
          AND status = 'Approved'
          AND employee = %(employee)s
          AND to_date >= %(start)s
          AND from_date <= %(end)s
    """,
        {"employee": employee, "start": start_date, "end": end_date},
        as_dict=True,
    )
    out = {}
    for r in rows:
        cur = max(getdate(r.from_date), start_date)
        last = min(getdate(r.to_date), end_date)
        half_day_date = getdate(r.half_day_date) if r.half_day and r.half_day_date else None
        while cur <= last:
            out[cur] = {
                "leave_type": r.leave_type,
                "half_day": bool(r.half_day and half_day_date == cur),
            }
            cur += timedelta(days=1)
    return out


def _checkin_map(employee, start_date, end_date):
    rows = frappe.db.sql(
        """
        SELECT DATE(time) AS d,
               SUM(CASE WHEN log_type='IN' THEN 1 ELSE 0 END) AS cnt_in,
               SUM(CASE WHEN log_type='OUT' THEN 1 ELSE 0 END) AS cnt_out
        FROM `tabEmployee Checkin`
        WHERE employee = %(employee)s
          AND time BETWEEN %(start)s AND %(end)s
        GROUP BY DATE(time)
    """,
        {
            "employee": employee,
            "start": datetime.combine(start_date, time.min),
            "end": datetime.combine(end_date, time.max),
        },
        as_dict=True,
    )
    return {
        getdate(r.d): {"cnt_in": int(r.cnt_in or 0), "cnt_out": int(r.cnt_out or 0)}
        for r in rows
    }


def _status_code_for_day(
    day,
    emp_doc,
    holiday_days,
    attendance_map,
    leave_map,
    checkin_map,
):
    doj = emp_doc.get("date_of_joining")
    doj = getdate(doj) if doj else None
    relieving = emp_doc.get("relieving_date")
    relieving = getdate(relieving) if relieving else None

    if doj and day < doj:
        return STATUS_CODE["CHƯA VÀO LÀM"]
    if relieving and day > relieving:
        return STATUS_CODE["VẮNG MẶT"]

    if day in holiday_days:
        return STATUS_CODE["NGHỈ LỄ"]
    if _is_weekend(day):
        return STATUS_CODE["CUỐI TUẦN"]

    att = attendance_map.get(day)
    if att:
        status = (att.get("status") or "").strip()
        if status in ("Present", "Work From Home", "Work From Office"):
            return STATUS_CODE["ĐI LÀM"]
        if status == "On Leave":
            leave_type = att.get("leave_type")
            return LEAVE_TYPE_CODE.get(leave_type, STATUS_CODE["NGHỈ PHÉP"])
        if status == "On Duty":
            return STATUS_CODE["VẮNG MẶT TẠI TRỤ SỞ CÔNG TY CÓ LÝ DO CÔNG VIỆC"]
        if status == "Half Day":
            return STATUS_CODE["NGHỈ NỬA NGÀY"]
        if status == "Absent":
            return STATUS_CODE["VẮNG MẶT"]
        return STATUS_CODE["VẮNG MẶT"]

    leave = leave_map.get(day)
    if leave:
        if leave.get("half_day"):
            return STATUS_CODE["NGHỈ NỬA NGÀY"]
        leave_type = leave.get("leave_type")
        return LEAVE_TYPE_CODE.get(leave_type, STATUS_CODE["NGHỈ PHÉP"])

    checkin = checkin_map.get(day)
    if checkin:
        ci, co = checkin["cnt_in"], checkin["cnt_out"]
        if ci > 0 and co > 0:
            return STATUS_CODE["ĐI LÀM"]
        return STATUS_CODE["QUÊN CHẤM CÔNG"]

    return STATUS_CODE["VẮNG MẶT"]


def _is_weekend(day):
    return day.weekday() >= 5

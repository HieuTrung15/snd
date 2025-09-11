import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin
from datetime import datetime, time, timedelta
from frappe.utils import today, getdate

class VntEmployeeCheckin(EmployeeCheckin):
    pass

DEVICE_IP   = "192.168.1.44"
DEVICE_PORT = 4370
COMM_KEY    = 123456
TIMEOUT_S   = 5

@frappe.whitelist()
def get_cham_cong():
    # Lấy ngày hôm nay dưới dạng date
    d = getdate(today())  # datetime.date(...)
    # Tạo khoảng thời gian theo datetime
    start_dt = datetime.combine(d, time.min)  # 00:00:00
    end_dt   = datetime.combine(d, time.max)  # 23:59:59.999999

    from zk import ZK
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=TIMEOUT_S, password=COMM_KEY,
            force_udp=False, ommit_ping=False)

    conn = zk.connect()
        # Khóa tạm trong lúc đọc (nếu thiết bị hỗ trợ)
    try:
        conn.disable_device()
    except Exception:
        pass

    raw_logs = conn.get_attendance() or []
    for att in raw_logs:
        ts = getattr(att, "timestamp", None)  # kiểu datetime từ lib pyzk
        if not ts:
            continue

        # (Tùy thiết bị) nếu ts có tz, chuẩn hóa về naive:
        # if getattr(ts, "tzinfo", None) is not None:
        #     ts = ts.astimezone().replace(tzinfo=None)

        if start_dt <= ts <= end_dt:
            emp = frappe.get_all(
                "Employee",
                filters={"attendance_device_id": str(getattr(att, "user_id", ""))},
                fields=["name", "employee_name", "custom_timekeeper_device"],
                limit=1,
            )
            if emp:
                frappe.get_doc({
                    "doctype": "Employee Checkin",
                    "employee": emp[0]["name"],
                    "employee_name": emp[0]["employee_name"],
                    "time": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "log_type": in_out(ts),  # truyền datetime trực tiếp
                }).insert(ignore_permissions=True)
    frappe.db.commit()

CUTOFF = time(11, 30, 0)

def in_out(ts):
    """
    ts: datetime | 'YYYY-MM-DD HH:MM:SS' | 'HH:MM:SS'
    rule: time >= 11:30:00 -> 'OUT', ngược lại -> 'IN'
    """
    if isinstance(ts, datetime):
        t = ts.time()
    else:
        s = str(ts).strip()
        fmt = "%Y-%m-%d %H:%M:%S" if " " in s else "%H:%M:%S"
        t = datetime.strptime(s, fmt).time()
    return "OUT" if t >= CUTOFF else "IN"

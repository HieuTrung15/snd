import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin
from datetime import datetime, time
from frappe.utils import today, getdate

class VntEmployeeCheckin(EmployeeCheckin):
    pass

DEVICE_IP   = "192.168.1.44"
DEVICE_PORT = 4370
COMM_KEY    = 123456
TIMEOUT_S   = 5

@frappe.whitelist()
def get_cham_cong():
    d_today = getdate(today())                 # ngày hôm nay (date)
    d_month_start = d_today.replace(day=1)     # ngày đầu tháng (date)

    start_dt = datetime.combine(d_month_start, time.min)  # 00:00:00 ngày 01
    end_dt   = datetime.combine(d_today, time.max)     # 23:59:59.999999 hôm nay

    # Kết nối và đọc dữ liệu từ thiết bị chấm công
    from zk import ZK
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=TIMEOUT_S, password=COMM_KEY,
            force_udp=False, ommit_ping=False)

    conn = None
    try:
        conn = zk.connect()
        raw_logs = conn.get_attendance() or []
        rows = []
        for att in raw_logs:
            ts = getattr(att, "timestamp", None)
            if not ts:
                continue
            if start_dt <= ts <= end_dt:
                rows.append({
                    "user_id": str(getattr(att, "user_id", "")),
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": getattr(att, "status", ""),
                    "punch": getattr(att, "punch", ""),
                    "device_ip": DEVICE_IP,
                })

        rows.sort(key=lambda r: (r["user_id"], r["timestamp"]))

        for row in rows:
            emp = frappe.get_value(
                "Employee",
                {"attendance_device_id": row["user_id"]},
                ["name", "employee_name"],
                as_dict=True,
            )
            if not emp:
                continue

            row_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
            day_start = datetime.combine(row_time.date(), time.min)
            day_end   = datetime.combine(row_time.date(), time.max)
            log_type = in_out(row_time)

            #Nếu đã có bản ghi cùng employee + log_type trong NGÀY -> bỏ qua
            exists = frappe.db.get_value(
                "Employee Checkin",
                {
                    "employee": emp.name,
                    "log_type": log_type,
                    "time": ["between", [day_start, day_end]],
                },
                "name",
            )
            if exists:
                continue

            # Chưa có -> tạo mới
            doc = frappe.new_doc("Employee Checkin")
            doc.employee = emp.name
            doc.employee_name = emp.employee_name
            doc.time = row_time
            doc.log_type = log_type
            doc.insert(ignore_permissions=True)

        frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"Lỗi khi kết nối/đọc dữ liệu: {e}", "get_cham_cong")
    finally:
        if conn:
            try: conn.enable_device()
            except Exception: pass
            try: conn.disconnect()
            except Exception: pass

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

import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin
from datetime import datetime, time
from frappe.utils import today, getdate
from zk import ZK

class VntEmployeeCheckin(EmployeeCheckin):
    pass

@frappe.whitelist()
def get_cham_cong():
    d_today = getdate(today())                 # ngày hôm nay (date)
    d_month_start = d_today.replace(day=1)     # ngày đầu tháng (date)

    start_dt = datetime.combine(d_month_start, time.min)  # 00:00:00 ngày 01
    end_dt   = datetime.combine(d_today, time.max)     # 23:59:59.999999 hôm nay
    # lay ra thong tin may cham cong
    devices = _device_list()
    for d in devices:
        rows.extend(_fetch_from_device(
            ip=d["ip"],
            port=d["port"],
            comm_key=d.get("comm_key") or 0,
            start_dt=start_dt,
            end_dt=end_dt,
            device_name=d["name"]
        ))
    # loc emp theo may cham cong
    rows = []
    if not rows:
        frappe.msgprint(_("Không có dữ liệu chấm công nào được lấy từ máy chấm công."))
        return
    for row in rows:
        emp = frappe.get_value(
            "Employee",
            {
                "attendance_device_id": row["user_id"],
                "custom_timekeeper_device": row["device_name"]
            },
            ["name", "employee_name"],
            as_dict=True,
        )
        if not emp:
            continue

        row_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        log_type = _in_out(row_time)
        # insert vào employee checkin
        doc = frappe.new_doc("Employee Checkin")
        doc.employee = emp.name
        doc.employee_name = emp.employee_name
        doc.time = row_time
        doc.log_type = log_type
        doc.insert(ignore_permissions=True)

    frappe.db.commit()


def _device_list():
    return frappe.get_all('Timekeeper Config', filters={'is_active': 1}, fields=['ip', 'port', 'comm_key', 'name'])


def _fetch_from_device(ip: str, port: int, comm_key: int, start_dt: datetime, end_dt: datetime, device_name: str):
    """Kết nối 1 thiết bị và trả về list rows đã lọc theo khoảng thời gian."""
    from zk import ZK
    zk = ZK(ip, port=port, timeout=5, password=comm_key, force_udp=False, ommit_ping=False)
    conn, out = None, []
    try:
        conn = zk.connect()
        raw_logs = conn.get_attendance() or []
        for att in raw_logs:
            ts = getattr(att, "timestamp", None)
            if not ts:
                continue
            if start_dt <= ts <= end_dt:
                out.append({
                    "user_id": str(getattr(att, "user_id", "")),
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": getattr(att, "status", ""),
                    "punch": getattr(att, "punch", ""),
                    "device_ip": ip,
                    "device_name": device_name
                })
    except Exception as e:
        frappe.log_error(f"[{ip}] Lỗi khi kết nối/đọc dữ liệu: {e}", "get_cham_cong_multi")
    finally:
        if conn:
            try: conn.enable_device()
            except Exception: pass
            try: conn.disconnect()
            except Exception: pass
    return out


CUTOFF = time(11, 30, 0)
def _in_out(ts):
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

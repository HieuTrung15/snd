import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin
from datetime import datetime, time, date
from frappe.utils import today, getdate
from zk import ZK

class VntEmployeeCheckin(EmployeeCheckin):
    pass


# 101.99.7.232
# 118.70.128.34

@frappe.whitelist()
def get_timekeeping_data_morning():
    d_today = getdate(today())                 # ngày hôm nay (date)
    d_month_start = d_today.replace(day=1)     # ngày đầu tháng (date)

    start_dt = datetime.combine(d_month_start, time.min)  # 00:00:00 ngày 01
    end_dt   = datetime.combine(d_today, time.max)     # 23:59:59.999999 hôm nay

    # get_today = date.today()
    # start_dt = datetime.combine(get_today, time.min)
    # end_dt = datetime.combine(get_today, time.max)

    rows = []
    devices = _device_list()
    for d in devices:
        rows.extend(_fetch_from_device(
            ip=d["ip"],
            port=d["port"],
            comm_key=d.get("comm_key") or 0,
            start_dt=start_dt,
            end_dt=end_dt,
        ))
    if not rows:
        frappe.msgprint(_("Không có dữ liệu chấm công nào được lấy từ máy chấm công."))
        return
    for row in rows:
        emp = frappe.get_value(
            "Employee",
            {
                "attendance_device_id": row["user_id"],
                "status": "Active",
            },
            ["name", "employee_name"],
            as_dict=True,
        )
        if not emp:
            continue

        row_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        exists = frappe.db.exists(
            "Employee Checkin",
            {"employee": emp.name, "log_type": "IN"}
        )
        if exists:
            continue

        # insert vào employee checkin
        doc = frappe.new_doc("Employee Checkin")
        doc.employee = emp.name
        doc.employee_name = emp.employee_name
        doc.time = row_time
        doc.log_type = "IN"
        doc.save()
    

@frappe.whitelist()
def get_timekeeping_data_evening():
    d_today = getdate(today())                 # ngày hôm nay (date)
    d_month_start = d_today.replace(day=1)     # ngày đầu tháng (date)

    start_dt = datetime.combine(d_month_start, time.min)  # 00:00:00 ngày 01
    end_dt   = datetime.combine(d_today, time.max)     # 23:59:59.999999 hôm nay
    # lay ra thong tin may cham cong
    # get_today = date.today()
    # start_dt = datetime.combine(get_today, time.min)
    # end_dt = datetime.combine(get_today, time.max)
    rows = []
    devices = _device_list()
    for d in devices:
        rows.extend(_fetch_from_device(
            ip=d["ip"],
            port=d["port"],
            comm_key=d.get("comm_key") or 0,
            start_dt=start_dt,
            end_dt=end_dt,
        ))
    # loc emp theo may cham cong
    if not rows:
        frappe.msgprint(_("Không có dữ liệu chấm công nào được lấy từ máy chấm công."))
        return
    emp_date_timestamps = {}
    for row in rows:
        emp = frappe.get_value(
            "Employee",
            {
                "attendance_device_id": row["user_id"],
                "status": "Active",
            },
            ["name", "employee_name"],
            as_dict=True,
        )
        if not emp:
            continue

        row_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        exists = frappe.db.exists(
            "Employee Checkin",
            {"employee": emp.name, "time": row_time}
        )
        if exists:
            continue

        # nhóm lại timestamps theo employee và date
        date_key = row_time.date()
        emp_key = emp.name
        if emp_key not in emp_date_timestamps:
            emp_date_timestamps[emp_key] = {}
        if date_key not in emp_date_timestamps[emp_key]:
            emp_date_timestamps[emp_key][date_key] = []
        emp_date_timestamps[emp_key][date_key].append((row_time, row, emp))
    
    for emp_key, dates in emp_date_timestamps.items():
        for date_key, entries in dates.items():
            if not entries:
                continue
            # tìm thời gian lớn nhất và nhỏ nhất trong ngày
            timestamps = [entry[0] for entry in entries]
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            for row_time, row, emp in entries:
                log_type = _in_out(row_time, min_ts, max_ts)
                # insert vào employee checkin
                doc = frappe.new_doc("Employee Checkin")
                doc.employee = emp.name
                doc.employee_name = emp.employee_name
                doc.time = row_time
                doc.log_type = log_type
                doc.save()


def _device_list():
    return frappe.get_all('Timekeeper Config', filters={'is_active': 1}, fields=['ip', 'port', 'comm_key', 'name'])


def _fetch_from_device(ip: str, port: int, comm_key: int, start_dt: datetime, end_dt: datetime):
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


def _in_out(ts: datetime, min_ts: datetime, max_ts: datetime):
    if ts == min_ts:
        return "IN"
    elif ts == max_ts:
        return "OUT"
    else:
        return ""

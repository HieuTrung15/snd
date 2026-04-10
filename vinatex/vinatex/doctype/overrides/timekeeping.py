import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin
from datetime import datetime, time, date, timedelta
from frappe.utils import today, getdate
from zk import ZK

class VntEmployeeCheckin(EmployeeCheckin):
    pass


# 101.99.7.232
# 118.70.128.34

@frappe.whitelist()
def create_allocation_nghi_con_ket_hon():
    today = date.today()
    from_date = date(today.year, 1, 1)
    to_date = date(today.year, 12, 31)
    employee = frappe.get_all("Employee",filters={"status": "Active"},pluck="name")
        
    for emp in employee:
        if frappe.db.exists("Leave Allocation", {'employee': emp, 'leave_type': 'Nghỉ con kết hôn', 'from_date': from_date, 'to_date': to_date}):
            continue
        doc = frappe.new_doc("Leave Allocation")
        doc.employee = emp
        doc.leave_type = 'Nghỉ con kết hôn'
        doc.from_date = from_date
        doc.to_date = to_date
        doc.new_leaves_allocated = 1
        doc.total_leaves_allocated = 1
        doc.save()


@frappe.whitelist()
def sync_timekeeper_data():
    """
    Hợp nhất và tối ưu hóa việc đồng bộ dữ liệu chấm công sáng/tối.
    Tự động tính toán và gán nhãn Vào (IN) / Ra (OUT) chính xác nhất dựa trên 
    thời điểm quẹt thẻ đầu tiên và cuối cùng trong ngày.
    """
    d_today = getdate(today())
    # Mặc định lấy từ đầu tháng. Nếu chạy vào ngày 01,
    # cần kéo thêm ngày cuối tháng trước để tránh mất dữ liệu.
    start_date = d_today.replace(day=1)
    if d_today.day == 1:
        start_date = d_today - timedelta(days=1)

    start_dt = datetime.combine(start_date, time.min)
    end_dt   = datetime.combine(d_today, time.max)

    rows = _collect_unique_rows(start_dt=start_dt, end_dt=end_dt)
    if not rows:
        # frappe.msgprint(_("Không có dữ liệu chấm công nào được lấy từ máy chấm công."))
        return

    # Cache danh sách nhân viên đang hoạt động để tra cứu nhanh
    employees = frappe.get_all("Employee", filters={"status": "Active"}, 
                               fields=["name", "employee_name", "attendance_device_id", "branch"])
    emp_device_map = {(str(e.attendance_device_id), e.branch): e for e in employees}
    emp_name_map = {e.name: e for e in employees}

    # Gom nhóm dữ liệu mới theo nhân viên và ngày
    new_data_groups = {}
    for row in rows:
        emp = emp_device_map.get((row["user_id"], row["branch"]))
        if not emp: continue
        
        ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        new_data_groups.setdefault((emp.name, ts.date()), set()).add(ts)

    # Thống kê kết quả
    inserted = 0
    updated = 0

    for (emp_name, d_date), new_ts_set in new_data_groups.items():
        day_start = datetime.combine(d_date, time.min)
        day_end = datetime.combine(d_date, time.max)
        
        # Lấy dữ liệu đã tồn tại trong DB của ngày này
        existing = frappe.get_all(
            "Employee Checkin",
            filters={"employee": emp_name, "time": ["between", [day_start, day_end]]},
            fields=["name", "time", "log_type"],
            order_by="time asc"
        )
        existing_map = {ec.time: ec for ec in existing}

        # Tập hợp tất cả các mốc thời gian (cũ + mới)
        all_ts = sorted(set(existing_map.keys()) | new_ts_set)
        if not all_ts: continue
        
        first_ts = all_ts[0]
        last_ts = all_ts[-1] if len(all_ts) > 1 else None
        emp_info = emp_name_map.get(emp_name)

        for ts in all_ts:
            expected_type = ""
            if ts == first_ts:
                expected_type = "IN"
            elif last_ts and ts == last_ts:
                expected_type = "OUT"

            ec_doc = existing_map.get(ts)
            if ec_doc:
                if ec_doc.log_type != expected_type:
                    frappe.db.set_value("Employee Checkin", ec_doc.name, "log_type", expected_type, update_modified=False)
                    updated += 1
            else:
                doc = frappe.new_doc("Employee Checkin")
                doc.employee = emp_name
                doc.employee_name = emp_info.employee_name
                doc.time = ts
                doc.log_type = expected_type
                doc.save()
                inserted += 1
    
    frappe.db.commit()
    return {
        "Số bản ghi đã tạo": inserted,
        "Số bản ghi đã cập nhật": updated
    }


def _device_list():
    return frappe.get_all('VNT Timekeeper Config', filters={'is_active': 1}, fields=['ip', 'port', 'comm_key', 'name', 'branch'])


def _collect_unique_rows(start_dt: datetime, end_dt: datetime):
    """lấy dữ liệu từ tất cả các máy chấm công, sau đó loại bỏ các bản ghi trùng nhau."""
    rows, seen = [], set()
    for d in _device_list():
        device_rows = _fetch_from_device(
            ip=d["ip"],
            port=d["port"],
            comm_key=d.get("comm_key") or 0,
            start_dt=start_dt,
            end_dt=end_dt,
            branch=d["branch"],
        )
        for row in device_rows:
            key = (row["user_id"], row["timestamp"], row["branch"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _fetch_from_device(ip: str, branch: str, port: int, comm_key: int, start_dt: datetime, end_dt: datetime):
    """Kết nối 1 thiết bị và trả về list rows đã lọc theo khoảng thời gian."""
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
                    "branch": branch
                })
    except Exception as e:
        frappe.log_error(f"[{ip}] Lỗi khi kết nối/đọc dữ liệu: {e}", "get_cham_cong_multi")
    finally:
        if conn:
            try:
                conn.enable_device()
            except Exception:
                pass
            try:
                conn.disconnect()
            except Exception:
                pass
    return out


def _in_out(ts: datetime, min_ts: datetime, max_ts: datetime):
    if ts == min_ts:
        return "IN"
    elif ts == max_ts:
        return "OUT"
    else:
        return ""

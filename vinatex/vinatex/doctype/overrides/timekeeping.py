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

    # start_dt = datetime.combine(d_month_start, time.min)  # 00:00:00 ngày 01

    start_dt = datetime.combine(date(2025, 9, 1), time.min)  # 2025-09-01 00:00:00
    end_dt   = datetime.combine(d_today, time.max)     # 23:59:59.999999 hôm nay
    # end_dt   = datetime.combine(date(2025, 9, 30), time.max)

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
            branch=d["branch"]
        ))
    if not rows:
        frappe.msgprint(_("Không có dữ liệu chấm công nào được lấy từ máy chấm công."))
        return
	
    processed = 0
    skipped_no_emp = 0
    skipped_exists = 0
    inserted = 0
    marked_in = 0

    # Gom nhóm theo employee + date
    emp_date_map = {}
    for row in rows:
        processed += 1
        emp = frappe.get_value(
            "Employee",
            {
                "attendance_device_id": row["user_id"],
                "status": "Active",
                "branch": row["branch"]
            },
            ["name", "employee_name"],
            as_dict=True,
        )
        if not emp:
            skipped_no_emp += 1
            continue

        row_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        if frappe.db.exists("Employee Checkin", {"employee": emp.name, "time": row_time}):
            skipped_exists += 1
            continue

        date_key = row_time.date()
        emp_key = emp.name
        emp_date_map.setdefault(emp_key, {}).setdefault(date_key, []).append((row_time, emp))
    for emp_key, dates in emp_date_map.items():
        for date_key, entries in dates.items():
            if not entries:
                continue
            entries.sort(key=lambda x: x[0])
            first_ts = entries[0][0]
            first_assigned = False
            for ts, emp in entries:
                doc = frappe.new_doc("Employee Checkin")
                doc.employee = emp.name
                doc.employee_name = emp.employee_name
                doc.time = ts
                # Chỉ gán IN cho timestamp đầu tiên trong ngày nếu chưa tồn tại IN nào trước đó trong ngày
                if not first_assigned:
                    # Kiểm tra đã có IN trong ngày này chưa
                    day_start = datetime.combine(date_key, time.min)
                    day_end = datetime.combine(date_key, time.max)
                    existing_in = frappe.get_all(
                        "Employee Checkin",
                        filters={
                            "employee": emp.name,
                            "log_type": "IN",
                            "time": ["between", [day_start, day_end]],
                        },
                        limit=1,
                    )
                    if not existing_in and ts == first_ts:
                        doc.log_type = "IN"
                        first_assigned = True
                        marked_in += 1
                    else:
                        doc.log_type = ""
                else:
                    doc.log_type = ""
                doc.save()
                inserted += 1


@frappe.whitelist()
def get_timekeeping_data_evening():
    d_today = getdate(today())                 # ngày hôm nay (date)
    d_month_start = d_today.replace(day=1)     # ngày đầu tháng (date)

    # start_dt = datetime.combine(d_month_start, time.min)  # 00:00:00 ngày 01

    start_dt = datetime.combine(date(2025, 9, 1), time.min)  # 2025-09-01 00:00:00
    end_dt   = datetime.combine(d_today, time.max)     # 23:59:59.999999 hôm nay
    # end_dt   = datetime.combine(date(2025, 9, 30), time.max)
    # Lấy dữ liệu mới từ thiết bị
    rows = []
    devices = _device_list()
    for d in devices:
        rows.extend(_fetch_from_device(
            ip=d["ip"],
            port=d["port"],
            comm_key=d.get("comm_key") or 0,
            start_dt=start_dt,
            end_dt=end_dt,
            branch=d["branch"]
        ))
    if not rows:
        frappe.msgprint(_("Không có dữ liệu chấm công nào được lấy từ máy chấm công."))
        return

    # biến đếm
    processed = 0
    skipped_no_emp = 0
    created = 0
    updated_out = 0
    updated_in = 0
    unchanged = 0

    # Gom nhóm timestamp mới theo employee + date
    new_emp_date = {}
    for row in rows:
        processed += 1
        emp = frappe.get_value(
            "Employee",
            {
                "attendance_device_id": row["user_id"],
                "status": "Active",
                "branch": row["branch"]
            },
            ["name", "employee_name"],
            as_dict=True,
        )
        if not emp:
            skipped_no_emp += 1
            continue
        ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        new_emp_date.setdefault(emp.name, {}).setdefault(ts.date(), set()).add(ts)

    # Với mỗi employee + date có dữ liệu mới: lấy lại toàn bộ checkin hiện có trong ngày để xác định first/last tại thời điểm hiện tại
    for emp_name, dates in new_emp_date.items():
        for d_date, new_ts_set in dates.items():
            # Lấy checkin đã có trong DB của ngày
            day_start = datetime.combine(d_date, time.min)
            day_end = datetime.combine(d_date, time.max)
            existing = frappe.get_all(
                "Employee Checkin",
                filters={
                    "employee": emp_name,
                    "time": ["between", [day_start, day_end]],
                },
                fields=["name", "time", "log_type"],
                order_by="time asc"
            )
            existing_map = {ec.time: ec for ec in existing}

            # Tập timestamp hợp nhất
            all_ts = set(existing_map.keys()) | new_ts_set
            ordered = sorted(all_ts)
            if not ordered:
                continue
            first_ts = ordered[0]
            last_ts = ordered[-1]

            # gán IN cho first_ts => chỉ khi chưa có IN nào trong ngày
            first_doc = existing_map.get(first_ts)
            if first_doc:
                if first_doc.log_type not in ("IN",):
                    frappe.db.set_value("Employee Checkin", first_doc.name, "log_type", "IN")
                    updated_in += 1
            else:
                emp_doc = frappe.get_doc("Employee", emp_name)
                doc = frappe.new_doc("Employee Checkin")
                doc.employee = emp_name
                doc.employee_name = emp_doc.employee_name
                doc.time = first_ts
                doc.log_type = "IN"
                doc.save()
                created += 1

            # gán OUT cho last_ts (chỉ nếu khác first_ts) => chỉ khi chưa có OUT nào trong ngày
            if last_ts != first_ts:
                last_doc = existing_map.get(last_ts)
                if last_doc:
                    if last_doc.log_type != "OUT":
                        frappe.db.set_value("Employee Checkin", last_doc.name, "log_type", "OUT")
                        updated_out += 1
                else:
                    emp_doc = frappe.get_doc("Employee", emp_name)
                    doc = frappe.new_doc("Employee Checkin")
                    doc.employee = emp_name
                    doc.employee_name = emp_doc.employee_name
                    doc.time = last_ts
                    doc.log_type = "OUT"
                    doc.save()
                    created += 1

            # Các timestamp giữa: tạo nếu chưa có (log_type giữ rỗng)
            middle_ts = [ts for ts in ordered if ts not in (first_ts, last_ts)]
            for mts in middle_ts:
                if mts in existing_map:
                    unchanged += 1
                    continue
                emp_doc = frappe.get_doc("Employee", emp_name)
                doc = frappe.new_doc("Employee Checkin")
                doc.employee = emp_name
                doc.employee_name = emp_doc.employee_name
                doc.time = mts
                doc.log_type = ""
                doc.save()
                created += 1



def _device_list():
    return frappe.get_all('Timekeeper Config', filters={'is_active': 1}, fields=['ip', 'port', 'comm_key', 'name', 'branch'])


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

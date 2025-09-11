import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin
from frappe.utils import get_date_str
import datetime
from dateutil.relativedelta import relativedelta 
from datetime import date
import sys

class VntEmployeeCheckin(EmployeeCheckin):
    pass


DEVICE_IP   = "192.168.1.44"
DEVICE_PORT = 4370
COMM_KEY    = 123456       # mật khẩu/comm-key của thiết bị
TIMEOUT_S   = 10


@frappe.whitelist()
def get_cham_cong():
    current_date = datetime.datetime.now() - datetime.timedelta(days=1)
    start_datetime = datetime.datetime(day= current_date.day, month = current_date.month, 
        year = current_date.year)
    end_datetime = datetime.datetime(day = current_date.day, month = current_date.month,
        year = current_date.year)+ relativedelta(days=1)
    start_datetime_format = ""
    end_datetime_format = ""
    
    start_dt, end_dt = start_datetime, end_datetime
    try:
        from zk import ZK
    except ImportError:
        print("Chưa cài pyzk. Hãy chạy: pip install pyzk")
        sys.exit(1)

    zk = ZK(
        DEVICE_IP,
        port=DEVICE_PORT,
        timeout=TIMEOUT_S,
        password=COMM_KEY, 
        force_udp=False,
        ommit_ping=False
    )

    conn = zk.connect()
    # Khuyến nghị khóa tạm khi đọc
    try:
        conn.disable_device()
    except Exception:
        pass
    # Thiết bị không filter theo thời gian được; ta kéo hết rồi lọc
    raw_logs = conn.get_attendance() or []

    rows = []
    for att in raw_logs:
        ts = getattr(att, "timestamp", None)
        if not ts:
            continue
        if start_dt <= ts <= end_dt:
            rows.append({
                "user_id": getattr(att, "user_id", ""),
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "status": getattr(att, "status", ""),
                "punch": getattr(att, "punch", ""),
                "device_ip": DEVICE_IP
            })

    rows.sort(key=lambda r: (r["user_id"], r["timestamp"]))
    frappe.throw(f"{rows}")
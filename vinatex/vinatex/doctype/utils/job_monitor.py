import frappe
import traceback
from datetime import datetime
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs

def log_and_notify(job_name, func, notify_on_success=True):
    """Bao bọc job để bắt lỗi và gửi thông báo trạng thái."""
    try:
        result = func()
        
        # Xác định trạng thái và thông tin chi tiết
        status = "PASS"
        details = ""
        
        if isinstance(result, dict):
            details = ", ".join([f"{k}: {v}" for k, v in result.items() if k != "status"])
            # Kiểm tra xem có dữ liệu nào được xử lý/tạo mới không
            counts = [v for k, v in result.items() if isinstance(v, int) and k != "total_employees"]
            if counts and sum(counts) == 0:
                status = "NO DATA"
        elif isinstance(result, (list, int)):
            count = result if isinstance(result, int) else len(result)
            details = f"Records: {count}"
            if count == 0:
                status = "NO DATA"
        
        if notify_on_success:
            send_notification(job_name, status, details or str(result))
        return result
    except Exception as e:
        # Trường hợp Job bị lỗi (FAIL) - Gửi chi tiết lỗi để xử lý
        error_log = traceback.format_exc()
        send_notification(job_name, "FAIL", f"Lỗi: {str(e)}", body=f"<b>Chi tiết lỗi:</b><br><pre>{error_log}</pre>")
        
        # QUAN TRỌNG: Cần commit để bản ghi thông báo không bị rollback khi raise lỗi ra ngoài
        frappe.db.commit()
        raise e

def send_notification(job_name, status, message, body=None):
    """Gửi thông báo vào Notification Log."""
    subject = f"🔔 [{status}] {job_name}: {message}"
    msg_body = body or f"<b>{job_name}</b> kết thúc lúc {datetime.now().strftime('%H:%M:%S')}<br><b>Trạng thái:</b> {status}<br><b>Chi tiết:</b> {message}"
    
    make_notification_logs({
        "type": "Alert",
        "subject": subject,
        "message": msg_body,
    }, ["hieutt@vinatex.com.vn", "tuandv@vinatex.com.vn", "sonph@vinatex.com.vn"])

# --- Các hàm Wrapper trỏ từ hooks.py ---

def monitor_sync_timekeeper_morning():
    from vinatex.vinatex.doctype.overrides.timekeeping import sync_timekeeper_data
    # Chỉ gửi thông báo vào 9:30 và 10:30
    notify = datetime.now().strftime("%H:%M") in ["09:30", "10:30"]
    return log_and_notify("Đồng bộ máy chấm công", sync_timekeeper_data, notify_on_success=notify)


def monitor_sync_timekeeper_evening():
    from vinatex.vinatex.doctype.overrides.timekeeping import sync_timekeeper_data
    # Chỉ gửi thông báo vào 9:30 và 10:30
    notify = datetime.now().strftime("%H:%M") in ["09:30", "10:30"]
    return log_and_notify("Đồng bộ máy chấm công", sync_timekeeper_data, notify_on_success=notify)

def monitor_create_attendance():
    from vinatex.vinatex.doctype.overrides.attendance import create_attendance_from_checkin
    return log_and_notify("Tạo Attendance từ Checkin", create_attendance_from_checkin)

def monitor_attendance_confirm():
    from vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm import make_attendance_confirm
    return log_and_notify("Tạo xác nhận công", make_attendance_confirm)

@frappe.whitelist()
def test_fail_notification():
    """Hàm test để mô phỏng một Job bị lỗi."""
    def func_error():
        raise Exception("Đây là lỗi giả lập để kiểm tra thông báo FAIL!")
    
    return log_and_notify("Job Test Lỗi", func_error)

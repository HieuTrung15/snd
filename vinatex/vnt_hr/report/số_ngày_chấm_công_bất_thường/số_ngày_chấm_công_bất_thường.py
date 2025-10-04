# report: Abnormal Attendance Days (This Month)
import frappe
from frappe.utils import get_first_day, get_last_day, getdate, today, cint

def execute(filters=None):
    """
    Trả về 1 ô duy nhất 'value' = số ngày bất thường trong THÁNG:
      - Đếm các ngày trong tháng
      - Loại bỏ ngày Holiday (theo Holiday List của Employee; nếu không có, fallback Company)
      - Loại bỏ ngày có Attendance (bất kể status)
      - Loại bỏ ngày nghỉ theo Leave Application:
          + full-day: trừ 1
          + half-day: trừ 0.5 (nếu half_day_date trùng ngày)
    Optional filters:
      {"month": 9, "year": 2025}
      {"from_date": "2025-09-01", "to_date": "2025-09-30"}
      {"employee": "EMP-0001"}  # nếu muốn kiểm tra cho người khác (quyền phù hợp)
    """
    if isinstance(filters, str):
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            filters = None
    filters = filters or {}

    # Map user -> employee
    employee = filters.get("employee") or frappe.db.get_value(
        "Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
    )
    if not employee:
        return _columns(), [{"value": 0.0}], None

    # Khoảng tính
    if filters.get("from_date") and filters.get("to_date"):
        start_date = getdate(filters["from_date"])
        end_date   = getdate(filters["to_date"])
    else:
        ref_date = getdate(today())
        month = cint(filters.get("month") or 0)
        year  = cint(filters.get("year")  or 0)
        if month and year:
            start_date = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
        else:
            start_date = get_first_day(ref_date)
        # Chỉ lấy đến ngày hiện tại thôi, không kéo tới hết tháng
        end_date = min(get_last_day(start_date), ref_date)


    if end_date < start_date:
        return _columns(), [{"value": 0.0}], None

    # Holiday List: ưu tiên của Employee, fallback Company
    emp_company, emp_holiday_list = frappe.db.get_value(
        "Employee", employee, ["company", "holiday_list"]
    )
    if not emp_holiday_list and emp_company:
        emp_holiday_list = frappe.db.get_value("Company", emp_company, "default_holiday_list")

    params = {
        "employee": employee,
        "from": start_date,
        "to": end_date,
        "holiday_list": emp_holiday_list or "",  # nếu rỗng => join sẽ không match
    }

    # Tính tổng bất thường:
    #  - Nếu là holiday -> 0
    #  - Nếu có Attendance -> 0
    #  - Nếu có Leave full-day -> 0
    #  - Nếu có Leave half-day (đúng ngày) -> 0.5
    #  - Else -> 1
    sql = """
    WITH RECURSIVE dates(d) AS (
        SELECT %(from)s
        UNION ALL
        SELECT DATE_ADD(d, INTERVAL 1 DAY) FROM dates WHERE d < %(to)s
    )
    SELECT
        SUM(
            CASE
                WHEN h.holiday_date IS NOT NULL THEN 0
                WHEN a.attendance_date IS NOT NULL THEN 0
                WHEN la_full.name IS NOT NULL THEN 0
                WHEN la_half.name IS NOT NULL THEN 0.5
                ELSE 1
            END
        ) AS value
    FROM dates dt
    LEFT JOIN `tabHoliday` h
        ON %(holiday_list)s <> ''
       AND h.parenttype = 'Holiday List'
       AND h.parent     = %(holiday_list)s
       AND h.holiday_date = dt.d
    LEFT JOIN `tabAttendance` a
        ON a.employee = %(employee)s
       AND a.docstatus = 1
       AND a.attendance_date = dt.d
    LEFT JOIN `tabLeave Application` la_full
        ON la_full.employee = %(employee)s
       AND la_full.docstatus = 1
       AND la_full.status = 'Approved'
       AND IFNULL(la_full.half_day, 0) = 0
       AND la_full.from_date <= dt.d
       AND la_full.to_date   >= dt.d
    LEFT JOIN `tabLeave Application` la_half
        ON la_half.employee = %(employee)s
       AND la_half.docstatus = 1
       AND la_half.status = 'Approved'
       AND IFNULL(la_half.half_day, 0) = 1
       AND la_half.half_day_date = dt.d
    WHERE dt.d BETWEEN %(from)s AND %(to)s
    """
    val = frappe.db.sql(sql, params, as_dict=True)[0].value or 0.0
    return _columns(), [{"value": float(val)}], None


def _columns():
    # Number Card sẽ lấy ô đầu tiên (cột 'value')
    return [{
        "label": "Abnormal Days",
        "fieldname": "value",
        "fieldtype": "Float",
        "width": 150,
    }]

# file: erpnext/[app]/[module]/report/bao_cao_lao_dong_binh_quan/bao_cao_lao_dong_binh_quan.py
import re
import frappe
from datetime import date
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP


def _parse_month(s: str) -> date:
    """Parse 'MM/YYYY' or 'YYYY-MM' -> first day of month (date)."""
    if not s or not isinstance(s, str):
        frappe.throw("Vui lòng nhập tháng dạng MM/YYYY hoặc YYYY-MM.")
    s = s.strip()
    m = re.fullmatch(r"(\d{2})/(\d{4})", s)
    if m:
        mm, yyyy = int(m.group(1)), int(m.group(2))
        return date(yyyy, mm, 1)
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        yyyy, mm = int(m.group(1)), int(m.group(2))
        return date(yyyy, mm, 1)
    frappe.throw(f"Không nhận dạng tháng: {s}. Dùng MM/YYYY hoặc YYYY-MM.")


def _add_months(d: date, n: int) -> date:
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return date(y, m, 1)


def execute(filters=None):
    f = filters or {}
    from_month = _parse_month(f.get("from_month"))
    to_month = _parse_month(f.get("to_month"))
    company = f.get("company")

    if from_month > to_month:
        frappe.throw("From Month phải nhỏ hơn hoặc bằng To Month.")

    # Build danh sách tháng (đầu tháng, cuối tháng)
    months = []
    cur = from_month
    while cur <= to_month:
        last_day = monthrange(cur.year, cur.month)[1]
        months.append((cur, date(cur.year, cur.month, last_day)))
        cur = _add_months(cur, 1)

    # Prefetch Employee giao thoa với toàn kỳ để giảm dữ liệu
    period_start = months[0][0]
    period_end = months[-1][1]
    where = """
        (COALESCE(date_of_joining, '0001-01-01') <= %(period_end)s)
        AND (relieving_date IS NULL OR relieving_date >= %(period_start)s)
    """
    params = {"period_start": period_start, "period_end": period_end}
    if company:
        where += " AND company = %(company)s"
        params["company"] = company

    emps = frappe.db.sql(
        f"""
        SELECT name, date_of_joining, relieving_date
        FROM `tabEmployee`
        WHERE {where}
        """,
        params,
        as_dict=True,
    )

    # Đếm: 1 nhân sự được tính vào tháng nếu tồn tại ít nhất 1 ngày trong tháng
    data = []
    for idx, (m_start, m_end) in enumerate(months, start=1):
        cnt = 0
        for e in emps:
            doj = e.date_of_joining
            rd = e.relieving_date
            if doj and doj > m_end:
                continue
            if rd is not None and rd < m_start:
                continue
            cnt += 1
        data.append({
            "month_label": f"{m_start:%m/%Y}",
            "headcount": cnt,
        })

    # Lao động bình quân (round half up)
    total = sum(r["headcount"] for r in data)
    n_months = len(data) or 1
    avg_headcount = int(Decimal(total / n_months).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    columns = [
        {"label": "Tháng", "fieldname": "month_label", "fieldtype": "Data", "width": 110},
        {"label": "Số lao động", "fieldname": "headcount", "fieldtype": "Int", "width": 120},
    ]

    message = f"Lao động bình quân: <b>{avg_headcount}</b>"
    return columns, data, message

import frappe
from frappe.utils import getdate
from datetime import datetime, timedelta, time
import json

@frappe.whitelist()
def get_vnt_car_registration_events(start, end, filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")

    rows = frappe.db.sql("""
        SELECT
            item.name   AS item_name,
            item.parent AS registration_id,
            item.date   AS trip_date,
            item.time   AS trip_time,
            item.driver AS driver
        FROM `tabVNT Car Registration Item` item
        WHERE item.date BETWEEN %(start)s AND %(end)s
        ORDER BY item.date, item.time
    """, {"start": start, "end": end}, as_dict=True)
    events = []
    for r in rows:
        if not (r.trip_date and r.trip_time):
            continue

        # --- ép kiểu time ngắn gọn ---
        t = r.trip_time
        if isinstance(t, timedelta):
            t = (datetime.min + t).time()
        elif isinstance(t, str):
            # "HH:MM:SS" (nếu format khác thì chỉnh lại cho đúng)
            t = datetime.strptime(t, "%H:%M:%S").time()

        start_dt = datetime.combine(getdate(r.trip_date), t)
        end_dt = start_dt + timedelta(hours=1)

        events.append({
            # mở FORM của phiếu cha khi click
            "name": r.registration_id,
            "doctype": "VNT Car Registration",
            "driver": r.driver,
            # hiển thị trên calendar
            "title": f"{start_dt.strftime('%H:%M')} | {r.driver or ''}",

            "start": start_dt,
            "end": end_dt,
            "allDay": 0,
        })
    return events

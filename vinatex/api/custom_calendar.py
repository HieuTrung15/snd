import frappe
from frappe.utils import getdate, add_days, add_months, nowdate

# ====== CONFIG: CÔNG TÁC (bạn chỉnh cho khớp doctype/field thực tế) ======
TRIP_PARENT_DOCTYPE = "VNT Business Trip Request"
TRIP_ITEM_DOCTYPE   = "VNT Business Trip Request Items"  # bạn có doctype này :contentReference[oaicite:5]{index=5}
TRIP_PARENTFIELD    = "items"                            # đổi nếu field table khác
TRIP_FROM_FIELD     = "from_date"                        # đổi nếu khác
TRIP_TO_FIELD       = "to_date"                          # đổi nếu khác
TRIP_DEST_FIELD     = "destination"                      # bạn yêu cầu hiển thị destination

# ====== CONFIG: HỌP ======
MEETING_DOCTYPE = "VNT Meeting Room Booking"
MEETING_LIST_EMP_CHILD = "VNT Car Registration Employee"  # options của list_emp :contentReference[oaicite:6]{index=6}
MEETING_LIST_EMP_PARENTFIELD = "list_emp"                 # fieldname list_emp :contentReference[oaicite:7]{index=7}


def _month_range(year: int, month: int):
    start = getdate(f"{year:04d}-{month:02d}-01")
    end = add_days(add_months(start, 1), -1)
    return start, end


def _get_user_department(user: str):
    emp = frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        ["name", "employee_name", "department"],
        as_dict=True
    )
    if not emp or not emp.get("department"):
        return None, emp
    return emp["department"], emp


def _push(dct: dict, date_key: str, kind: str, payload: dict):
    bucket = dct.setdefault(date_key, {"trips": [], "meetings": []})
    bucket[kind].append(payload)


@frappe.whitelist()
def get_department_calendar(year: int | None = None, month: int | None = None):
    """
    Calendar theo THÁNG cho PHÒNG BAN của user đăng nhập:
    - trips: công tác (destination)
    - meetings: họp (note)
    """
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Not permitted")

    today = getdate(nowdate())
    year = int(year or today.year)
    month = int(month or today.month)

    dept, emp = _get_user_department(user)
    if not dept:
        return {
            "department": None,
            "year": year,
            "month": month,
            "by_date": {},
            "note": "User chưa map được Employee.department (cần set Employee.user_id + department)."
        }

    start, end = _month_range(year, month)
    by_date: dict[str, dict] = {}

    # =========================
    # 1) CÔNG TÁC (theo dept)
    # =========================
    # NOTE: doctype/field công tác bạn cần chỉnh TRIP_* cho đúng schema thực tế.
    trip_sql = f"""
        SELECT
            t.name AS request_name,
            t.`{TRIP_FROM_FIELD}` AS from_date,
            t.`{TRIP_TO_FIELD}`   AS to_date,
            t.`{TRIP_DEST_FIELD}` AS destination,
            i.employee,
            i.employee_name,
            i.department
        FROM `tab{TRIP_PARENT_DOCTYPE}` t
        JOIN `tab{TRIP_ITEM_DOCTYPE}` i
          ON i.parent = t.name
         AND i.parenttype = %s
         AND i.parentfield = %s
        WHERE t.docstatus < 2
          AND i.department = %s
          AND t.`{TRIP_FROM_FIELD}` <= %s
          AND t.`{TRIP_TO_FIELD}`   >= %s
        ORDER BY t.`{TRIP_FROM_FIELD}` ASC, i.employee_name ASC
    """
    try:
        trip_rows = frappe.db.sql(
            trip_sql,
            (TRIP_PARENT_DOCTYPE, TRIP_PARENTFIELD, dept, end, start),
            as_dict=True
        )
    except Exception:
        trip_rows = []

    # gom theo request để tránh lặp (nhiều item cùng 1 request)
    trip_map = {}
    for r in trip_rows:
        key = r.request_name
        trip = trip_map.setdefault(key, {
            "request_name": r.request_name,
            "from_date": str(getdate(r.from_date)) if r.from_date else None,
            "to_date": str(getdate(r.to_date)) if r.to_date else None,
            "destination": r.destination,
            "people": []
        })
        trip["people"].append({
            "employee": r.employee,
            "employee_name": r.employee_name or r.employee
        })

    for trip in trip_map.values():
        fd = getdate(trip["from_date"])
        td = getdate(trip["to_date"])
        s = fd if fd > start else start
        e = td if td < end else end

        cur = s
        while cur <= e:
            k = cur.strftime("%Y-%m-%d")
            _push(by_date, k, "trips", trip)
            cur = add_days(cur, 1)

    # =========================
    # 2) HỌP (VNT Meeting Room Booking)
    # =========================
    # Booking có department fetch_from employee.department :contentReference[oaicite:8]{index=8}
    bookings = frappe.get_all(
        MEETING_DOCTYPE,
        filters={
            "department": dept,
            "workflow_state": "Đã duyệt",
            "docstatus": 1,
            "date": ["between", [start, end]],
        },
        fields=["name", "date", "start_time", "end_time", "room_name", "note", "employee", "employee_name"],
        order_by="date asc, start_time asc",
    )

    if bookings:
        booking_names = [b["name"] for b in bookings]

        # list_emp là Table MultiSelect :contentReference[oaicite:9]{index=9}
        list_rows = frappe.get_all(
            MEETING_LIST_EMP_CHILD,
            filters={
                "parenttype": MEETING_DOCTYPE,
                "parentfield": MEETING_LIST_EMP_PARENTFIELD,
                "parent": ["in", booking_names],
            },
            fields=["parent", "employee"],
        )

        # map parent -> set(employee_id)
        peep = {}
        for r in list_rows:
            peep.setdefault(r.parent, set()).add(r.employee)

        # cache employee_name
        emp_ids = set()
        for b in bookings:
            if b.get("employee"):
                emp_ids.add(b["employee"])
        for sset in peep.values():
            emp_ids |= set(sset)

        emp_name_map = {}
        if emp_ids:
            emp_name_map = dict(
                frappe.get_all("Employee", filters={"name": ["in", list(emp_ids)]}, fields=["name", "employee_name"], as_list=1)
            )

        for b in bookings:
            k = getdate(b["date"]).strftime("%Y-%m-%d")

            # danh sách người họp = người đề xuất + list_emp (giống logic notify đang duyệt list_emp) :contentReference[oaicite:10]{index=10}
            participants = []
            seen = set()

            def add_emp(eid):
                if not eid or eid in seen:
                    return
                seen.add(eid)
                participants.append({
                    "employee": eid,
                    "employee_name": emp_name_map.get(eid) or eid
                })

            add_emp(b.get("employee"))
            for eid in sorted(peep.get(b["name"], set())):
                add_emp(eid)

            _push(by_date, k, "meetings", {
                "booking_name": b["name"],
                "date": str(getdate(b["date"])),
                "start_time": b.get("start_time"),
                "end_time": b.get("end_time"),
                "room_name": b.get("room_name"),
                "note": b.get("note"),  # note là “Nội dung cuộc họp” :contentReference[oaicite:11]{index=11}
                "people": participants,
            })

    return {
        "department": dept,
        "year": year,
        "month": month,
        "by_date": by_date
    }

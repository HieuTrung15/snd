import frappe
from frappe.utils import getdate, add_days, add_months, nowdate

# ====== CONFIG: CÔNG TÁC (bạn chỉnh cho khớp doctype/field thực tế) ======
TRIP_PARENT_DOCTYPE = "VNT Business Trip Request"
TRIP_ITEM_DOCTYPE   = "VNT Business Trip Request Items"  
TRIP_PARENTFIELD    = "items"                            
TRIP_FROM_FIELD     = "from_date"                        
TRIP_TO_FIELD       = "to_date"                          
TRIP_DEST_FIELD     = "destination"                      

# ====== CONFIG: HỌP ======
MEETING_DOCTYPE = "VNT Meeting Room Booking"
MEETING_LIST_EMP_CHILD = "VNT Car Registration Employee"  
MEETING_LIST_EMP_PARENTFIELD = "list_emp"                

# ====== CONFIG: LÃNH ĐẠO TẬP ĐOÀN ======
LEADER_DESIGNATIONS = {
    "Chủ tịch Hội đồng quản trị Tập đoàn",
    "Tổng Giám đốc Tập đoàn",
    "Phó Tổng Giám đốc Tập đoàn",
    "Giám đốc điều hành Tập đoàn",
}
LEADER_DESIGNATION_ORDER = {
    "Chủ tịch Hội đồng quản trị Tập đoàn": 0,
    "Tổng Giám đốc Tập đoàn": 1,
    "Phó Tổng Giám đốc Tập đoàn": 2,
    "Giám đốc điều hành Tập đoàn": 3,
}

# ====== CONFIG: LỊCH CÔNG TÁC TUẦN LÃNH ĐẠO ======
LEADER_WEEKLY_TRIP_PARENT_DOCTYPE = "VNT Leader Weekly Trip"
LEADER_WEEKLY_TRIP_ITEM_DOCTYPE = "VNT Leader Weekly Trip Item"
LEADER_WEEKLY_TRIP_PARENTFIELD = "items"


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
    bucket = dct.setdefault(
        date_key,
        {"trips": [], "meetings": [], "leader_trips": [], "leader_leaves": [], "leaves": []},
    )
    bucket[kind].append(payload)


def _get_leader_employees():
    if not LEADER_DESIGNATIONS:
        return {}
    rows = frappe.get_all(
        "Employee",
        filters={"status": "Active", "designation": ("in", list(LEADER_DESIGNATIONS))},
        fields=["name", "employee_name", "designation"],
        ignore_permissions=True,
    )
    return {r.name: r for r in rows}


def _add_date_range(by_date: dict, start, end, kind: str, payload: dict):
    cur = start
    while cur <= end:
        k = cur.strftime("%Y-%m-%d")
        _push(by_date, k, kind, payload)
        cur = add_days(cur, 1)


def _sort_people_by_leader_order(people: list[dict], leader_map: dict) -> list[dict]:
    def sort_key(item: dict):
        leader = leader_map.get(item.get("employee") or "") or {}
        designation = leader.get("designation") or ""
        return (LEADER_DESIGNATION_ORDER.get(designation, 99), item.get("employee_name") or "")

    return sorted(people or [], key=sort_key)


@frappe.whitelist()
def get_department_calendar(year: int | None = None, month: int | None = None):
    """
    Calendar theo THÁNG cho PHÒNG BAN của user đăng nhập:
    - trips: công tác (destination)
    - meetings: họp (note)
    - leader_trips: công tác của lãnh đạo tập đoàn + lịch công tác tuần lãnh đạo
    - leader_leaves: nghỉ của lãnh đạo tập đoàn
    """
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Not permitted")

    today = getdate(nowdate())
    year = int(year or today.year)
    month = int(month or today.month)

    start, end = _month_range(year, month)
    by_date: dict[str, dict] = {}
    common_by_date: dict[str, dict] = {}
    personal_by_date: dict[str, dict] = {}

    dept, emp = _get_user_department(user)
    has_dept = bool(dept)

    # =========================
    # 1) CÔNG TÁC (theo dept)
    # =========================
    if has_dept:
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
              AND t.workflow_state = %s
              AND i.department = %s
              AND t.`{TRIP_FROM_FIELD}` <= %s
              AND t.`{TRIP_TO_FIELD}`   >= %s
            ORDER BY t.`{TRIP_FROM_FIELD}` ASC, i.employee_name ASC
        """
        try:
            trip_rows = frappe.db.sql(
                trip_sql,
                (TRIP_PARENT_DOCTYPE, TRIP_PARENTFIELD, "Đã duyệt", dept, end, start),
                as_dict=True,
            )
        except Exception:
            trip_rows = []

        # gom theo request để tránh lặp (nhiều item cùng 1 request)
        trip_map = {}
        for r in trip_rows:
            key = r.request_name
            trip = trip_map.setdefault(
                key,
                {
                    "request_name": r.request_name,
                    "from_date": str(getdate(r.from_date)) if r.from_date else None,
                    "to_date": str(getdate(r.to_date)) if r.to_date else None,
                    "destination": r.destination,
                    "people": [],
                },
            )
            trip["people"].append(
                {"employee": r.employee, "employee_name": r.employee_name or r.employee}
            )

        for trip in trip_map.values():
            fd = getdate(trip["from_date"])
            td = getdate(trip["to_date"])
            s = fd if fd > start else start
            e = td if td < end else end
            _add_date_range(by_date, s, e, "trips", trip)
            _add_date_range(common_by_date, s, e, "trips", trip)

    # =========================
    # 2) HỌP (VNT Meeting Room Booking)
    # =========================
    # Booking có department fetch_from employee.department 
    if has_dept:
        bookings = frappe.get_all(
            MEETING_DOCTYPE,
            filters={
                "department": dept,
                "workflow_state": "Đã duyệt",
                "docstatus": 1,
                "date": ["between", [start, end]],
            },
            fields=[
                "name",
                "date",
                "start_time",
                "end_time",
                "room_name",
                "note",
                "employee",
                "employee_name",
            ],
            order_by="date asc, start_time asc",
        )

        if bookings:
            booking_names = [b["name"] for b in bookings]

            # list_emp là Table MultiSelect 
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
                    frappe.get_all(
                        "Employee",
                        filters={"name": ["in", list(emp_ids)]},
                        fields=["name", "employee_name"],
                        as_list=1,
                    )
                )

            for b in bookings:
                k = getdate(b["date"]).strftime("%Y-%m-%d")

                # danh sách người họp = người đề xuất + list_emp (giống logic notify đang duyệt list_emp) 
                participants = []
                seen = set()

                def add_emp(eid):
                    if not eid or eid in seen:
                        return
                    seen.add(eid)
                    participants.append(
                        {"employee": eid, "employee_name": emp_name_map.get(eid) or eid}
                    )

                add_emp(b.get("employee"))
                for eid in sorted(peep.get(b["name"], set())):
                    add_emp(eid)

                _push(
                    by_date,
                    k,
                    "meetings",
                    {
                        "booking_name": b["name"],
                        "date": str(getdate(b["date"])),
                        "start_time": b.get("start_time"),
                        "end_time": b.get("end_time"),
                        "room_name": b.get("room_name"),
                        "note": b.get("note"),
                        "people": participants,
                    },
                )
                _push(
                    common_by_date,
                    k,
                    "meetings",
                    {
                        "booking_name": b["name"],
                        "date": str(getdate(b["date"])),
                        "start_time": b.get("start_time"),
                        "end_time": b.get("end_time"),
                        "room_name": b.get("room_name"),
                        "note": b.get("note"),
                        "people": participants,
                    },
                )

    # =========================
    # 3) LÃNH ĐẠO (công tác / nghỉ)
    # =========================
    leader_map = _get_leader_employees()
    leader_ids = list(leader_map.keys())

    if leader_ids:
        # 3.1) Nghỉ (Leave Application)
        leave_rows = frappe.get_all(
            "Leave Application",
            filters={
                "employee": ["in", leader_ids],
                "workflow_state": "Đã duyệt",
                "docstatus": 1,
                "from_date": ["<=", end],
                "to_date": [">=", start],
            },
            fields=[
                "name",
                "employee",
                "employee_name",
                "from_date",
                "to_date",
                "leave_type",
                "description",
                "half_day",
                "half_day_date",
            ],
            order_by="from_date asc",
        )

        for row in leave_rows:
            if not row.get("from_date") or not row.get("to_date"):
                continue
            leader = leader_map.get(row.employee) or {}
            payload = {
                "leave_name": row.get("name"),
                "employee": row.get("employee"),
                "employee_name": row.get("employee_name") or leader.get("employee_name") or row.get("employee"),
                "from_date": str(getdate(row.get("from_date"))) if row.get("from_date") else None,
                "to_date": str(getdate(row.get("to_date"))) if row.get("to_date") else None,
                "leave_type": row.get("leave_type"),
                "description": row.get("description"),
                "half_day": row.get("half_day"),
                "half_day_date": str(getdate(row.get("half_day_date"))) if row.get("half_day_date") else None,
                "people": [
                    {
                        "employee": row.get("employee"),
                        "employee_name": row.get("employee_name")
                        or leader.get("employee_name")
                        or row.get("employee"),
                    }
                ],
            }
            fd = getdate(payload["from_date"])
            td = getdate(payload["to_date"])
            s = fd if fd > start else start
            e = td if td < end else end
            _add_date_range(by_date, s, e, "leader_leaves", payload)
            _add_date_range(common_by_date, s, e, "leader_leaves", payload)

        # 3.2) Công tác (VNT Business Trip Request)
        placeholders = ", ".join(["%s"] * len(leader_ids))
        leader_trip_sql = f"""
            SELECT
                t.name AS request_name,
                t.`{TRIP_FROM_FIELD}` AS from_date,
                t.`{TRIP_TO_FIELD}`   AS to_date,
                t.`{TRIP_DEST_FIELD}` AS destination,
                i.employee,
                i.employee_name
            FROM `tab{TRIP_PARENT_DOCTYPE}` t
            JOIN `tab{TRIP_ITEM_DOCTYPE}` i
              ON i.parent = t.name
             AND i.parenttype = %s
             AND i.parentfield = %s
            WHERE t.docstatus < 2
              AND t.workflow_state = %s
              AND i.employee IN ({placeholders})
              AND t.`{TRIP_FROM_FIELD}` <= %s
              AND t.`{TRIP_TO_FIELD}`   >= %s
            ORDER BY t.`{TRIP_FROM_FIELD}` ASC, i.employee_name ASC
        """
        try:
            leader_trip_rows = frappe.db.sql(
                leader_trip_sql,
                (
                    TRIP_PARENT_DOCTYPE,
                    TRIP_PARENTFIELD,
                    "Đã duyệt",
                    *leader_ids,
                    end,
                    start,
                ),
                as_dict=True,
            )
        except Exception:
            leader_trip_rows = []

        leader_trip_map = {}
        for r in leader_trip_rows:
            key = r.request_name
            trip = leader_trip_map.setdefault(
                key,
                {
                    "request_name": r.request_name,
                    "from_date": str(getdate(r.from_date)) if r.from_date else None,
                    "to_date": str(getdate(r.to_date)) if r.to_date else None,
                    "destination": r.destination,
                    "people": [],
                },
            )
            trip["people"].append(
                {
                    "employee": r.employee,
                    "employee_name": r.employee_name or r.employee,
                }
            )

        for trip in leader_trip_map.values():
            trip["people"] = _sort_people_by_leader_order(trip["people"], leader_map)
            fd = getdate(trip["from_date"])
            td = getdate(trip["to_date"])
            s = fd if fd > start else start
            e = td if td < end else end
            _add_date_range(by_date, s, e, "leader_trips", trip)
            _add_date_range(common_by_date, s, e, "leader_trips", trip)

    # 3.3) Lịch công tác tuần của lãnh đạo (doctype phụ)
    leader_weekly_trip_sql = f"""
        SELECT
            t.name AS request_name,
            t.creation AS parent_creation,
            t.from_date AS parent_from_date,
            t.to_date AS parent_to_date,
            i.trip_date,
            i.idx AS row_idx,
            i.time_slot,
            i.destination,
            i.purpose,
            i.employee,
            i.employee_name
        FROM `tab{LEADER_WEEKLY_TRIP_PARENT_DOCTYPE}` t
        JOIN `tab{LEADER_WEEKLY_TRIP_ITEM_DOCTYPE}` i
          ON i.parent = t.name
         AND i.parenttype = %s
         AND i.parentfield = %s
        WHERE t.docstatus < 2
          AND (
            (i.trip_date IS NOT NULL AND i.trip_date BETWEEN %s AND %s)
            OR (i.trip_date IS NULL AND t.from_date <= %s AND t.to_date >= %s)
          )
        ORDER BY
            COALESCE(i.trip_date, t.from_date) ASC,
            t.creation ASC,
            i.idx ASC,
            i.creation ASC
    """
    try:
        leader_weekly_trip_rows = frappe.db.sql(
            leader_weekly_trip_sql,
            (
                LEADER_WEEKLY_TRIP_PARENT_DOCTYPE,
                LEADER_WEEKLY_TRIP_PARENTFIELD,
                start,
                end,
                end,
                start,
            ),
            as_dict=True,
        )
    except Exception:
        leader_weekly_trip_rows = []

    leader_weekly_trip_map = {}
    for row in leader_weekly_trip_rows:
        trip_date = getdate(row.trip_date) if row.trip_date else None
        parent_from_date = getdate(row.parent_from_date) if row.parent_from_date else None
        parent_to_date = getdate(row.parent_to_date) if row.parent_to_date else None

        from_date = trip_date or parent_from_date
        to_date = trip_date or parent_to_date
        if not from_date or not to_date:
            continue

        destination = (row.destination or "").strip() or "(chưa có địa điểm)"
        purpose = (row.purpose or "").strip()
        time_slot = (row.time_slot or "").strip() or "Cả ngày"
        if time_slot in {"Sáng", "Chiều"}:
            destination = f"[{time_slot}] {destination}"

        key = (
            row.request_name,
            str(from_date),
            str(to_date),
            destination,
            purpose,
            time_slot,
        )
        trip = leader_weekly_trip_map.setdefault(
            key,
            {
                "request_name": row.request_name,
                "from_date": str(from_date),
                "to_date": str(to_date),
                "destination": destination,
                "purpose": purpose,
                "time_slot": time_slot,
                "people": [],
            },
        )
        trip["people"].append(
            {
                "employee": row.employee,
                "employee_name": row.employee_name or row.employee,
            }
        )

    for trip in leader_weekly_trip_map.values():
        fd = getdate(trip["from_date"])
        td = getdate(trip["to_date"])
        s = fd if fd > start else start
        e = td if td < end else end
        _add_date_range(by_date, s, e, "leader_trips", trip)
        _add_date_range(common_by_date, s, e, "leader_trips", trip)

    # 3.4) Lịch cá nhân (Leave + Trip + Meeting)
    if emp and emp.get("name"):
        emp_id = emp.get("name")

        personal_leaves = frappe.get_all(
            "Leave Application",
            filters={
                "employee": emp_id,
                "workflow_state": "Đã duyệt",
                "docstatus": 1,
                "from_date": ["<=", end],
                "to_date": [">=", start],
            },
            fields=[
                "name",
                "employee",
                "employee_name",
                "from_date",
                "to_date",
                "leave_type",
                "description",
                "half_day",
                "half_day_date",
            ],
            order_by="from_date asc",
        )

        for row in personal_leaves:
            if not row.get("from_date") or not row.get("to_date"):
                continue
            payload = {
                "leave_name": row.get("name"),
                "employee": row.get("employee"),
                "employee_name": row.get("employee_name") or row.get("employee"),
                "from_date": str(getdate(row.get("from_date"))) if row.get("from_date") else None,
                "to_date": str(getdate(row.get("to_date"))) if row.get("to_date") else None,
                "leave_type": row.get("leave_type"),
                "description": row.get("description"),
                "half_day": row.get("half_day"),
                "half_day_date": str(getdate(row.get("half_day_date"))) if row.get("half_day_date") else None,
                "people": [
                    {
                        "employee": row.get("employee"),
                        "employee_name": row.get("employee_name") or row.get("employee"),
                    }
                ],
            }
            fd = getdate(payload["from_date"])
            td = getdate(payload["to_date"])
            s = fd if fd > start else start
            e = td if td < end else end
            _add_date_range(personal_by_date, s, e, "leaves", payload)

        # Personal trips (VNT Business Trip Request Items)
        personal_trip_sql = f"""
            SELECT
                t.name AS request_name,
                t.`{TRIP_FROM_FIELD}` AS from_date,
                t.`{TRIP_TO_FIELD}`   AS to_date,
                t.`{TRIP_DEST_FIELD}` AS destination,
                i.employee,
                i.employee_name
            FROM `tab{TRIP_PARENT_DOCTYPE}` t
            JOIN `tab{TRIP_ITEM_DOCTYPE}` i
              ON i.parent = t.name
             AND i.parenttype = %s
             AND i.parentfield = %s
            WHERE t.docstatus < 2
              AND t.workflow_state = %s
              AND i.employee = %s
              AND t.`{TRIP_FROM_FIELD}` <= %s
              AND t.`{TRIP_TO_FIELD}`   >= %s
            ORDER BY t.`{TRIP_FROM_FIELD}` ASC, i.employee_name ASC
        """
        try:
            personal_trip_rows = frappe.db.sql(
                personal_trip_sql,
                (TRIP_PARENT_DOCTYPE, TRIP_PARENTFIELD, "Đã duyệt", emp_id, end, start),
                as_dict=True,
            )
        except Exception:
            personal_trip_rows = []

        personal_trip_map = {}
        for r in personal_trip_rows:
            key = r.request_name
            trip = personal_trip_map.setdefault(
                key,
                {
                    "request_name": r.request_name,
                    "from_date": str(getdate(r.from_date)) if r.from_date else None,
                    "to_date": str(getdate(r.to_date)) if r.to_date else None,
                    "destination": r.destination,
                    "people": [],
                },
            )
            trip["people"].append(
                {"employee": r.employee, "employee_name": r.employee_name or r.employee}
            )

        for trip in personal_trip_map.values():
            fd = getdate(trip["from_date"])
            td = getdate(trip["to_date"])
            s = fd if fd > start else start
            e = td if td < end else end
            _add_date_range(personal_by_date, s, e, "trips", trip)

        # Personal meetings (participant or booker)
        personal_bookings = frappe.get_all(
            MEETING_DOCTYPE,
            filters={
                "workflow_state": "Đã duyệt",
                "docstatus": 1,
                "date": ["between", [start, end]],
                "employee": emp_id,
            },
            fields=[
                "name",
                "date",
                "start_time",
                "end_time",
                "room_name",
                "note",
                "employee",
                "employee_name",
            ],
            order_by="date asc, start_time asc",
        )

        personal_booking_names = [b["name"] for b in personal_bookings] if personal_bookings else []
        participant_bookings = set()
        if personal_booking_names:
            participant_bookings |= set(personal_booking_names)

        participant_rows = frappe.get_all(
            MEETING_LIST_EMP_CHILD,
            filters={
                "parenttype": MEETING_DOCTYPE,
                "parentfield": MEETING_LIST_EMP_PARENTFIELD,
                "employee": emp_id,
            },
            fields=["parent"],
        )
        for r in participant_rows:
            if r.get("parent"):
                participant_bookings.add(r["parent"])

        if participant_bookings:
            meeting_rows = frappe.get_all(
                MEETING_DOCTYPE,
                filters={
                    "name": ["in", list(participant_bookings)],
                    "workflow_state": "Đã duyệt",
                    "docstatus": 1,
                    "date": ["between", [start, end]],
                },
                fields=[
                    "name",
                    "date",
                    "start_time",
                    "end_time",
                    "room_name",
                    "note",
                    "employee",
                    "employee_name",
                ],
                order_by="date asc, start_time asc",
            )

            list_rows = frappe.get_all(
                MEETING_LIST_EMP_CHILD,
                filters={
                    "parenttype": MEETING_DOCTYPE,
                    "parentfield": MEETING_LIST_EMP_PARENTFIELD,
                    "parent": ["in", list(participant_bookings)],
                },
                fields=["parent", "employee"],
            )

            peep = {}
            for r in list_rows:
                peep.setdefault(r.parent, set()).add(r.employee)

            emp_ids = set()
            for b in meeting_rows:
                if b.get("employee"):
                    emp_ids.add(b["employee"])
            for sset in peep.values():
                emp_ids |= set(sset)

            emp_name_map = {}
            if emp_ids:
                emp_name_map = dict(
                    frappe.get_all(
                        "Employee",
                        filters={"name": ["in", list(emp_ids)]},
                        fields=["name", "employee_name"],
                        as_list=1,
                    )
                )

            for b in meeting_rows:
                k = getdate(b["date"]).strftime("%Y-%m-%d")
                participants = []
                seen = set()

                def add_emp(eid):
                    if not eid or eid in seen:
                        return
                    seen.add(eid)
                    participants.append(
                        {"employee": eid, "employee_name": emp_name_map.get(eid) or eid}
                    )

                add_emp(b.get("employee"))
                for eid in sorted(peep.get(b["name"], set())):
                    add_emp(eid)

                _push(
                    personal_by_date,
                    k,
                    "meetings",
                    {
                        "booking_name": b["name"],
                        "date": str(getdate(b["date"])),
                        "start_time": b.get("start_time"),
                        "end_time": b.get("end_time"),
                        "room_name": b.get("room_name"),
                        "note": b.get("note"),
                        "people": participants,
                    },
                )

    return {
        "department": dept if has_dept else None,
        "year": year,
        "month": month,
        "by_date": by_date,
        "common_by_date": common_by_date,
        "personal_by_date": personal_by_date,
        "note": None
        if has_dept
        else "User chưa map được Employee.department (cần set Employee.user_id + department).",
    }

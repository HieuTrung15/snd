import frappe
from frappe.model.document import Document
from frappe.utils import date_diff
from frappe.utils import getdate
from frappe.utils import nowdate
from datetime import timedelta

class VNTBusinessTripRequest(Document):

    def on_submit(self):
        leave_type = "Công tác"

        # Kiểm tra allow_over_allocation của leave type
        leave_type_doc = frappe.get_doc("Leave Type", leave_type)
        allow_over_allocation = leave_type_doc.allow_over_allocation

        for emp in self.items:  # bảng nhân viên
            employee = emp.employee
            company = self.company

            for t in self.time_leave:  # bảng thời gian
                from_date = t.from_date
                to_date = t.to_date
                type_leave = t.type_leave

                days_required = date_diff(to_date, from_date) + 1
                allocation_to_use = None

                # Nếu không cho phép over allocation thì check balance
                # if not allow_over_allocation:
                #     # Tính tổng ngày đã dùng
                #     leave_apps = frappe.get_all(
                #         "Leave Application",
                #         filters={
                #             "employee": employee,
                #             "leave_type": leave_type,
                #             "status": "Approved",
                #             "docstatus": 1
                #         },
                #         fields=["from_date", "to_date"]
                #     )

                #     leaves_taken = sum(date_diff(la["to_date"], la["from_date"]) + 1 for la in leave_apps)

                #     # Lấy allocation hiện có để tính balance
                #     allocations = frappe.get_all(
                #         "Leave Allocation",
                #         filters={
                #             "employee": employee,
                #             "leave_type": leave_type,
                #             "docstatus": 1
                #         },
                #         order_by="creation asc",
                #         fields=["name", "from_date", "to_date", "total_leaves_allocated"]
                #     )

                #     allocation_to_use = None
                #     balance = 0
                #     for a in allocations:
                #         a_balance = a["total_leaves_allocated"] - leaves_taken
                #         if a_balance >= days_required:
                #             allocation_to_use = a["name"]
                #             balance = a_balance
                #             break
                #         balance += a_balance
                #     from_date = getdate(t.from_date)
                #     to_date = getdate(t.to_date)

                #     # Nếu nửa ngày thì coi là cùng 1 ngày
                #     if type_leave in ["Sáng", "Chiều"] or from_date == to_date:
                #         to_date_for_allocation = from_date + timedelta(days=1)
                #     else:
                #         to_date_for_allocation = to_date

                #     if date_diff(to_date, from_date) < 0:
                #         frappe.throw(f"Invalid leave period for {employee}: {from_date} → {to_date}")
                #     # Nếu không đủ balance, tạo allocation mới
                #     from_date = getdate(t.from_date)
                #     to_date = getdate(t.to_date)
                #     if not allocation_to_use or balance < days_required:
                #         allocation_doc = frappe.new_doc("Leave Allocation")
                #         allocation_doc.employee = employee
                #         allocation_doc.leave_type = leave_type
                #         allocation_doc.from_date = from_date
                #         allocation_doc.to_date = to_date_for_allocation  # cộng thêm 1 ngày nếu cùng ngày
                #         allocation_doc.new_leaves_allocated = days_required
                #         allocation_doc.total_leaves_allocated = days_required  # quan trọng
                #         allocation_doc.company = company
                #         allocation_doc.insert()
                #         allocation_doc.submit()
                #         allocation_to_use = allocation_doc.name


                # Tạo Leave Application
                leave_doc = frappe.get_doc({
                    "doctype": "Leave Application",
                    "employee": employee,
                    "leave_type": leave_type,
                    "from_date": from_date,
                    "to_date": to_date,
                    "status": "Approved",
                    "leave_allocation": allocation_to_use  # có thể None nếu allow over allocation
                })

                # Nếu type_leave = Sáng/Chiều thì set half-day
                if type_leave in ["Sáng", "Chiều"]:
                    leave_doc.half_day = 1
                    leave_doc.half_day_date = from_date
                else:
                    leave_doc.half_day = 0

                leave_doc.insert()
                leave_doc.submit()
                
    def on_cancel(self):
        leave_type = "Công tác"

        for emp in self.items:  # bảng nhân viên
            employee = emp.employee

            for t in self.time_leave:  # bảng thời gian
                from_date = t.from_date
                to_date = t.to_date

                # Tìm Leave Application đã tạo
                leave_apps = frappe.get_all(
                    "Leave Application",
                    filters={
                        "employee": employee,
                        "leave_type": leave_type,
                        "from_date": from_date,
                        "to_date": to_date,
                        "status": "Approved",
                        "docstatus": 1
                    },
                    fields=["name"]
                )

                for la in leave_apps:
                    leave_doc = frappe.get_doc("Leave Application", la["name"])
                    leave_doc.cancel()

@frappe.whitelist()
def allocate_leave_for_all(
    leave_type="Công tác",
    target_days=100,
    year=None,
    from_date=None,
    to_date=None,
    company=None,        # lọc theo company (tùy chọn)
    department=None,     # lọc theo department (tùy chọn)
    employee_names=None, # list tên Employee cụ thể (tùy chọn)
    commit_every=50,     # tối ưu tốc độ
    dry_run=False        # True = chỉ báo cáo, không ghi DB
):
    # ---- Khung thời gian ----
    today = getdate(nowdate())
    if year is None and (from_date is None or to_date is None):
        year = today.year
    if from_date is None:
        from_date = getdate(f"{year}-01-01")
    else:
        from_date = getdate(from_date)
    if to_date is None:
        to_date = getdate(f"{year}-12-31")
    else:
        to_date = getdate(to_date)
 
    # ---- Đảm bảo Leave Type tồn tại ----
    if not frappe.db.exists("Leave Type", leave_type):
        if dry_run:
            print(f"[DRY RUN] Would create Leave Type '{leave_type}'")
        else:
            lt = frappe.get_doc({
                "doctype": "Leave Type",
                "leave_type_name": leave_type,
                "include_holiday": 0,
                "is_lwp": 0,  # đổi 1 nếu là nghỉ không lương
                "allow_encashment": 0,
            })
            lt.insert(ignore_permissions=True)
 
    # ---- Lấy danh sách nhân viên ----
    emp_filters = {"status": "Active"}
    if company:
        emp_filters["company"] = company
    if department:
        emp_filters["department"] = department
 
    emp_fields = ["name", "company"]
    employees = []
    if employee_names:
        # lọc theo list cung cấp
        employees = frappe.get_all("Employee", filters={"name": ["in", employee_names]}, fields=emp_fields)
    else:
        employees = frappe.get_all("Employee", filters=emp_filters, fields=emp_fields)
 
    if not employees:
        print("Không có nhân viên nào khớp bộ lọc.")
        return
 
    emp_names = [e["name"] for e in employees]
 
    # ---- Prefetch các allocation đang overlap để giảm query ----
    existing = frappe.get_all(
        "Leave Allocation",
        filters={
            "leave_type": leave_type,
            "employee": ["in", emp_names],
            "from_date": ["<=", to_date],
            "to_date":   [">=", from_date],
        },
        fields=["name", "employee", "docstatus", "from_date", "to_date", "new_leaves_allocated"]
    )
    # map: employee -> list allocation
    ex_map = {}
    for r in existing:
        ex_map.setdefault(r["employee"], []).append(r)
 
    created, amended, updated, skipped = 0, 0, 0, 0
    processed = 0
 
    for e in employees:
        emp = e["name"]
        comp = e["company"]
        rows = ex_map.get(emp, [])
 
        if rows:
            # lấy allocation đầu tiên (thông thường 1 bản/emp/kỳ)
            r = rows[0]
            if dry_run:
                print(f"[DRY RUN] {emp}: would normalize to {target_days} days ({from_date}→{to_date}) on {r['name']}")
                skipped += 1
            else:
                doc = frappe.get_doc("Leave Allocation", r["name"])
                if doc.docstatus == 1:
                    # Submitted: cancel & amend
                    doc.flags.ignore_permissions = True
                    doc.cancel()
                    new_doc = frappe.copy_doc(doc)
                    new_doc.set_new_name()
                    new_doc.amended_from = doc.name
                    new_doc.from_date = from_date
                    new_doc.to_date = to_date
                    new_doc.new_leaves_allocated = target_days
                    new_doc.insert(ignore_permissions=True)
                    new_doc.submit()
                    amended += 1
                else:
                    # Draft: cập nhật rồi submit
                    doc.new_leaves_allocated = target_days
                    doc.from_date = from_date
                    doc.to_date = to_date
                    doc.flags.ignore_permissions = True
                    doc.save()
                    if doc.docstatus == 0:
                        doc.submit()
                    updated += 1
        else:
            if dry_run:
                print(f"[DRY RUN] {emp}: would create allocation {target_days} days ({from_date}→{to_date})")
                created += 1
            else:
                alloc = frappe.get_doc({
                    "doctype": "Leave Allocation",
                    "employee": emp,
                    "company": comp,
                    "leave_type": leave_type,
                    "from_date": from_date,
                    "to_date": to_date,
                    "new_leaves_allocated": target_days,
                    "carry_forward": 0,
                    "description": f"Auto set {target_days} days for {leave_type} ({from_date}→{to_date})",
                })
                alloc.insert(ignore_permissions=True)
                alloc.submit()
                created += 1
 
        processed += 1
        if not dry_run and processed % commit_every == 0:
            frappe.db.commit()
            print(f"... committed {processed}/{len(employees)}")
 
    if not dry_run:
        frappe.db.commit()
 
    print(f"Done: total employees={len(employees)} | created={created} | amended={amended} | updated={updated} | skipped={skipped}")
    print(f"Leave Type='{leave_type}', target_days={target_days}, period={from_date}→{to_date}")
 
# ===== Ví dụ chạy nhanh =====
# allocate_leave_for_all()  # mặc định: 'Công tác', 100 ngày, năm hiện tại, mọi nhân viên Active
# allocate_leave_for_all(company="Vinatex")                  # chỉ 1 company
# allocate_leave_for_all(department="Kinh Doanh")            # lọc theo phòng ban
# allocate_leave_for_all(employee_names=["EMP-0001","EMP-0007"])  # chỉ vài người
# allocate_leave_for_all(target_days=120, year=2025)         # kỳ 2025 với 120 ngày
# allocate_leave_for_all(from_date="2025-04-01", to_date="2026-03-31")  # kỳ tùy chỉnh (ví dụ năm tài chính)
# allocate_leave_for_all(dry_run=True)                       # xem trước, không ghi DB
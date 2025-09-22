import frappe
from frappe.model.document import Document
from frappe.utils import date_diff
from frappe.utils import getdate
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

                frappe.msgprint(
                    f"Leave Application created for {employee}: {from_date} → {to_date}, {type_leave}"
                )
                
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
                    frappe.msgprint(
                        f"Leave Application cancelled for {employee}: {from_date} → {to_date}"
                    )
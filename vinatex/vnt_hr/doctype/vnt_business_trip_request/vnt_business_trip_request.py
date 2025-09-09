import frappe
from frappe.model.document import Document
from frappe.utils import getdate, date_diff

class VNTBusinessTripRequest(Document):

    def on_submit(self):
        leave_type = "Công tác"

        for item in self.items:
            employee = item.employee
            from_date = self.from_date
            to_date = self.to_date
            company = self.company

            days_required = date_diff(to_date, from_date) + 1

            # Lấy tất cả Leave Allocation đã submit cho employee
            allocations = frappe.get_all(
                "Leave Allocation",
                filters={
                    "employee": employee,
                    "leave_type": leave_type,
                    "docstatus": 1
                },
                order_by="creation asc",
                fields=["name", "from_date", "to_date", "total_leaves_allocated"]
            )

            allocation_to_use = None
            balance = 0

            for a in allocations:
                # Tính tổng số leave đã sử dụng cho allocation này
                leaves_taken = frappe.db.sql("""
                    SELECT SUM(total_leave_days) 
                    FROM `tabLeave Application`
                    WHERE leave_allocation=%s AND docstatus=1
                """, a["name"])[0][0] or 0

                a_balance = a["total_leaves_allocated"] - leaves_taken
                if a_balance >= days_required:
                    allocation_to_use = a["name"]
                    balance = a_balance
                    break
                balance += a_balance

            # Nếu không đủ, tạo allocation mới
            if not allocation_to_use or balance < days_required:
                allocation_doc = frappe.get_doc({
                    "doctype": "Leave Allocation",
                    "employee": employee,
                    "leave_type": leave_type,
                    "from_date": from_date,
                    "to_date": to_date,
                    "new_leaves_allocated": days_required,
                    "company": company
                })
                allocation_doc.insert()
                allocation_doc.submit()
                allocation_to_use = allocation_doc.name

            # Tạo Leave Application
            leave_doc = frappe.get_doc({
                "doctype": "Leave Application",
                "employee": employee,
                "leave_type": leave_type,
                "from_date": from_date,
                "to_date": to_date,
                "status": "Approved",
                "leave_allocation": allocation_to_use
            })
            leave_doc.insert()
            leave_doc.submit()
            frappe.msgprint(f"Leave Application created for {employee}: {from_date} to {to_date}")

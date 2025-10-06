import frappe
from frappe.model.document import Document
from frappe.utils import date_diff
from frappe.utils import getdate, add_days
from frappe.utils import nowdate
from datetime import timedelta

class VNTBusinessTripRequest(Document):

    def on_submit(self):
        leave_type = "Công tác"
        lstEmployee = [d.employee for d in (self.items or []) if d.employee]
        if self.employee:
            lstEmployee.append(self.employee)
        lstEmployee = list(set(lstEmployee))

        for employee in lstEmployee:
            company = self.company
            cur = getdate(self.from_date)
            to_date = getdate(self.to_date)

            while cur <= to_date:
                existing_name = frappe.db.exists("Attendance", {
                    "employee": employee,
                    "attendance_date": cur,
                    "docstatus": ["!=", 2]  # bỏ qua bản cancel
                })

                if existing_name:
                    att_doc = frappe.get_doc("Attendance", existing_name)
                    # cập nhật trạng thái & loại nghỉ
                    att_doc.db_set({
                        "status": "On Leave",
                        "leave_type": leave_type
                    })
                    cur = add_days(cur, 1)
                    continue

                # tạo mới nếu chưa có
                att = frappe.new_doc("Attendance")
                att.employee = employee
                att.company = company
                att.attendance_date = cur
                att.status = "On Leave"
                att.leave_type = leave_type
                att.insert()
                att.submit()

                cur = add_days(cur, 1)
        
                
    def on_cancel(self):
        leave_type = "Công tác"

        # Gom danh sách nhân viên: từ bảng + người tạo đơn, loại rỗng & trùng
        lstEmployee = list({getattr(d, "employee", None) for d in (self.items or []) if getattr(d, "employee", None)})
        if getattr(self, "employee", None):
            lstEmployee.append(self.employee)
        employees = list(set(lstEmployee))

        if not employees:
            return

        company = self.company
        start_date = getdate(self.from_date)
        end_date = getdate(self.to_date)


        for emp in employees:
            cur = start_date
            while cur <= end_date:
                filters = {
                    "employee": emp,
                    "attendance_date": cur,
                    "company": company,
                    "docstatus": 1,           # chỉ hủy các bản đã submit
                    "status": "On Leave",
                    "leave_type": leave_type,
                }

                # Lấy các bản Attendance khớp để hủy
                names = frappe.get_all("Attendance", filters=filters, pluck="name")

                for att_name in names:
                    att = frappe.get_doc("Attendance", att_name)
                    # Nếu muốn chắc cú chỉ hủy bản do đơn này sinh ra, có thể kiểm tra thêm điều kiện ở đây
                    att.cancel()

                cur = cur + timedelta(days=1)
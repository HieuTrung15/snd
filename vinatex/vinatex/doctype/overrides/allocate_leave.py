from hrms.hr.doctype.leave_allocation.leave_allocation import validate_carry_forward, get_unused_leaves
from vinatex.vinatex.doctype.overrides.leave_allocation import get_previous_allocation, Config
from frappe.utils.data import get_date_str, getdate
from frappe.model.meta import get_field_precision
from dateutil.relativedelta import relativedelta
from frappe.utils.logger import set_log_level
from frappe.utils import get_date_str, flt
from hrms.hr.utils import get_leave_period
from datetime import datetime, date, timedelta
import frappe


@frappe.whitelist()
def allocate_leave():
    """
    Tạo Leave Period cho cả năm và phân bổ Leave Policy + Leave Allocation cho
    nhân viên active nếu chưa tồn tại. Tránh return sớm trong vòng lặp;
    sử dụng continue để xử lý từng nhân viên.
    Trả về số record đã tạo.
    """
    leave_type = frappe.get_doc("Leave Type", Config.LEAVE_TYPE)

    from_date = date.today().replace(month=1, day=1)
    to_date = from_date + relativedelta(years=1, days=-1)

    leave_policy_name = frappe.get_value('Leave Policy', {'title': Config.LEAVE_POLICY_TITLE}, 'name')
    if not leave_policy_name:
        frappe.log_error(f"Leave Policy with title {Config.LEAVE_POLICY_TITLE} not found", "Allocate Leave Error")
        frappe.msgprint("Không tìm thấy Leave Policy cấu hình", alert=True, indicator="Red")
        return 0

    # Lấy giá trị annual_allocation từ Leave Policy Detail (map theo leave_type)
    lp_details = frappe.get_all(
        'Leave Policy Detail',
        filters={'parent': leave_policy_name},
        fields=['leave_type', 'annual_allocation']
    )
    policy_annual_map = {d['leave_type']: flt(d.get('annual_allocation', 0)) for d in lp_details}
    # tạo / lấy leave period cho cả năm
    leave_period = create_leave_period(from_date, to_date, Config.COMPANY)

    employees = frappe.get_all('Employee',
                               filters={'status': 'Active'},
                               fields=['name', 'employee_name', 'date_of_joining', 'company', 'department', 'holiday_list'])

    created_count = 0

    for emp in employees:
        emp_name = emp['name']

        # nếu đã có Leave Policy Assignment overlap với kỳ này và policy này -> skip employee
        existing_lpa = frappe.get_all(
            "Leave Policy Assignment",
            filters={
                "employee": emp_name,
                "docstatus": 1,
                "effective_to": (">=", from_date),
                "effective_from": ("<=", to_date),
                "leave_policy": leave_policy_name
            },
            pluck='name'
        )
        if existing_lpa:
            return
        # Tạo Leave Policy Assignment
        lpa = frappe.new_doc('Leave Policy Assignment')
        lpa.employee = emp_name
        lpa.assignment_based_on = "Leave Period"
        lpa.leave_policy = leave_policy_name
        lpa.effective_from = leave_period.from_date
        lpa.effective_to = leave_period.to_date
        # lpa.carry_forward = 1
        lpa.leave_period = leave_period.name
        lpa.docstatus = 1  # mark as submitted
        lpa.insert(ignore_permissions=True)
        frappe.db.commit()
        # mark as submitted/docstatus = 1 and set leaves_allocated to a sensible default (1 như trước nếu cần)
        frappe.db.set_value('Leave Policy Assignment', lpa.name, {'docstatus': 1, 'leaves_allocated': 1})
        created_count += 1

        # --- NEW: cập nhật Leave Allocation(s) sinh ra bởi lpa, gán annual_allocation -> new_leaves_allocated ---
        allocations = frappe.get_all(
            'Leave Allocation',
            filters={'leave_policy_assignment': lpa.name, 'docstatus': 1},
            fields=['name', 'leave_type']
        )
        # frappe.throw(f"{allocations}")
        if allocations:
            for alloc in allocations:
                ann = policy_annual_map.get(alloc['leave_type'], 0)
                # cập nhật cả new_leaves_allocated và total_leaves_allocated để đồng bộ
                frappe.db.set_value('Leave Allocation', alloc['name'],
                                {'new_leaves_allocated': ann})
                # commit optional
                frappe.db.commit()
    # phân bổ leave allocation cho nhân viên sẽ tính từ ngày joining để tính số ngày phép còn lại, những nhân viên vào từ năm 
    # ngoái sẽ 12 ngày phép
    # frappe.msgprint(f'Hoàn tất phân bổ: đã tạo {created_count} bản ghi cho {Config.LEAVE_POLICY_TITLE}', alert=True, indicator='Green')
    # return created_count


def create_leave_period(from_date, to_date, company):
    leave_period = get_leave_period(get_date_str(from_date), get_date_str(to_date), company)
    if leave_period:
        return leave_period[0]
    else:
        leave_period = frappe.get_doc(dict(
            doctype='Leave Period',
            from_date=from_date,
            to_date=to_date,
            company=company,
            is_active=1
        ))
        leave_period.save(ignore_permissions=True)
        return leave_period
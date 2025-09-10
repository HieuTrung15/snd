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
    leave_type = frappe.get_doc("Leave Type", Config.LEAVE_TYPE)
    from_date = date.today().replace(month=1, day=1)
    to_date = from_date + relativedelta(years=1, days=-1)

    # from_date = date.today().replace(day=1) 
    # to_date = from_date + relativedelta(months = 1, days = -1)

    leave_policy_name = frappe.get_value('Leave Policy', {'title': Config.LEAVE_POLICY_TITLE}, 'name')
    leave_policy_detail = frappe.get_doc('Leave Policy Detail', {'parent': leave_policy_name})
    # tao leave period cho ca năm
    leave_period = create_leave_period(from_date, to_date, Config.COMPANY)
    
    # lay danh sach nhan vien dang hoat dong
    employee = frappe.get_all('Employee', filters={'status': 'Active'}, fields=['name', 'employee_name', 'date_of_joining', 'company', 'department'])
    for emp in employee:
        leave_policy_assignments = frappe.get_all(
            "Leave Policy Assignment",
            filters={
                "employee": emp.name,
                "docstatus": 1,
                "effective_to": (">=", leave_period.from_date),
                "effective_from": ("<=", leave_period.to_date),
                'leave_policy': leave_policy_name
            },
            pluck='name'
        )
        if not len(leave_policy_assignments):
            lpa = frappe.new_doc('Leave Policy Assignment')
            lpa.employee = emp.name
            lpa.assignment_based_on =" Leave Period"
            lpa.leave_policy = leave_policy_name
            lpa.effective_from = leave_period.from_date
            lpa.effective_to = leave_period.to_date
            lpa.carry_forward = 1
            lpa.leave_period = leave_period.name
            lpa.docstatus = 1
            lpa.save(ignore_permissions=True)
            frappe.db.set_value('Leave Policy Assignment', lpa.name, {'docstatus': 1, 'leaves_allocated': 1})

            exist_allocate = frappe.get_all("Leave Allocation",filters={'employee':emp.name,'leave_type':leave_type.name, 'from_date':['Between',[from_date,to_date]],'docstatus':1}) \
                        + frappe.get_all("Leave Allocation",filters={'employee':emp.name,'leave_type':leave_type.name,'to_date':['Between',[from_date,to_date]],'docstatus':1}) 
            if exist_allocate:
                continue

            leave_allocation = frappe.get_all(
                "Leave Allocation",
                filters={
                    "employee": emp.name,
                    "docstatus": 1,
                    "from_date": (">=", leave_period.from_date),
                    "to_date": ("<=", leave_period.to_date),
                    'leave_policy': leave_policy_name
                },
                pluck='name'
            )
            if not len(leave_allocation):
                new_leave_allocation = frappe.new_doc('Leave Allocation')
                new_leave_allocation.employee = emp.name
                new_leave_allocation.leave_type = leave_type.name
                new_leave_allocation.from_date = from_date
                new_leave_allocation.to_date = to_date
                new_leave_allocation.leave_policy_assignment = lpa.name
                new_leave_allocation.new_leaves_allocated = leave_policy_detail.annual_allocation
                new_leave_allocation.total_leaves_allocated = leave_policy_detail.annual_allocation
                new_leave_allocation.carry_forward = 1
                new_leave_allocation.company = emp.company
                new_leave_allocation.department = emp.department
                new_leave_allocation.docstatus = 1
                new_leave_allocation.save(ignore_permissions=True)

    frappe.msgprint(f'Đã tạo phân bổ {Config.LEAVE_POLICY_TITLE} thành công',alert = True,indicator = 'Green')


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
# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from frappe import _
import frappe

def execute(filters=None):
        if not filters:
            filters = {}
        columns = get_columns(filters)
        data = get_data(filters)
        # chart = get_chart_data(data)       
        return columns, data, None

def get_columns(filters=None):
    columns = [
        {
            "label": _("Mã số Nhân viên"),
            "fieldname": "employee",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Tên Nhân viên"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Phòng/Ban"),
            "fieldname": "department",
            "fieldtype": "Data",
            "width": 150
        },
		{
            "label": _("Vị trí công việc"),
            "fieldname": "job_title",
            "fieldtype": "Data",
            "width": 150
        },
		{
            "label": _("Chức danh"),
            "fieldname": "designation",
            "fieldtype": "Data",
            "width": 150
        },
		
		{
            "label": _("Loại hợp đồng"),
            "fieldname": "type",
            "fieldtype": "Data",
            "width": 200
        },
		{
            "label": _("Lý do ký lại HĐ"),
            "fieldname": "sign_reason",
            "fieldtype": "Data",
            "width": 100
        },
		{
            "label": _("Ngày bắt đầu"),
            "fieldname": "from_date",
            "fieldtype": "Date",
            "width": 120
        },
		{
            "label": _("Ngày kết thúc"),
            "fieldname": "to_date",
            "fieldtype": "Date",
            "width": 120
        },
		{
            "label": _("Ngày ký"),
            "fieldname": "contract_date",
            "fieldtype": "Date",
            "width": 120
        },

		{
            "label": _("Người ký"),
            "fieldname": "signer",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Vị trí công việc người ký"),
            "fieldname": "designation_of_signer",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Trạng thái"),
            "fieldname": "sign_status",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Số quyết định lương cơ bản"),
            "fieldname": "salary_decision_num",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Đối tượng lương"),
            "fieldname": "salary_beneficiary",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Tên thang bảng lương"),
            "fieldname": "salary_scale_name",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Ngạch lương"),
            "fieldname": "salary_grade",
            "fieldtype": "Int",
            "width": 120
        },
		{
            "label": _("Bậc lương"),
            "fieldname": "salary_step",
            "fieldtype": "Int",
            "width": 120
        },
		{
            "label": _("Hệ số"),
            "fieldname": "salary_coefficient",
            "fieldtype": "Int",
            "width": 120
        },
		{
            "label": _("Lương cơ bản"),
            "fieldname": "basic_salary",
            "fieldtype": "Int",
            "width": 120
        },
		{
            "label": _("Phụ cấp kiêm nhiệm"),
            "fieldname": "concurrent_allowance",
            "fieldtype": "Int",
            "width": 120
        }
    ]
    return columns

def get_data(filters=None):
    data = []
    conditions = get_filter_conditions(filters)	
    sql = f"""      
        SELECT 
			emp.name as employee,
			emp.employee_name as employee_name,
			emp.department as department,
			ct.job_title as job_title,
			emp.designation as designation,
			ct.type as type,
			ct.sign_reason as sign_reason,
			ct.from_date as from_date,
			ct.to_date as to_date,
			ct.contract_date as contract_date,
			ct.employee as signer,
			ct.designation as designation_of_signer,
			ct.sign_status as sign_status,
			ct.salary_decision_num as salary_decision_num,
			ct.salary_beneficiary as salary_beneficiary,
			ct.salary_scale_name as salary_scale_name,
			ct.salary_grade as salary_grade,
			ct.salary_step as salary_step,
			ct.salary_coefficient as salary_coefficient,
			ct.basic_salary as basic_salary,
			ct.concurrent_allowance as concurrent_allowance
        FROM
            `tabEmployee` emp
			LEFT JOIN `tabVNT Contract` ct ON ct.parent = emp.name
        WHERE 
            emp.status != 'Left'
            {conditions}
        """
    return frappe.db.sql(sql, as_dict=True)
  
#customize: Lọc dữ liệu
def get_filter_conditions(filters):
    conditions = ""   
    # if filters.get("employee"):
    #     conditions += " and emp.employee = '%s' " % (filters.get("employee"))
    # if filters.get("company"):
    #     conditions += " and emp.company = '%s' " % (filters.get("company"))
    # if filters.get("department"):
    #     conditions += " and emp.department = '%s' " % (filters.get("department"))
	# if filters.get("type"):
	# 	conditions += " and emp.department = '%s' " % (filters.get("department"))
    return conditions 

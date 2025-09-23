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
            "label": _("Mã số Nhân sự"),
            "fieldname": "employee",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Tên Nhân sự"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 120
        },
		{
            "label": _("Chức danh"),
            "fieldname": "designation",
            "fieldtype": "Data",
            "width": 150
        },
		{
            "label": _("Phòng/Ban"),
            "fieldname": "department",
            "fieldtype": "Data",
            "width": 150
        },
		{
            "label": _("Công ty"),
            "fieldname": "company",
            "fieldtype": "Data",
            "width": 200
        },
		{
            "label": _("Chi nhánh"),
            "fieldname": "branch",
            "fieldtype": "Data",
            "width": 100
        },
		{
            "label": _("Số điện thoại"),
            "fieldname": "phone",
            "fieldtype": "Phone",
            "width": 120
        },
		{
            "label": _("Email"),
            "fieldname": "company_email",
            "fieldtype": "Data",
            "width": 200
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
			emp.designation as designation,
			emp.department as department,
			emp.company as company,
			emp.branch as branch,
			emp.cell_number as phone,
			emp.company_email as company_email
        FROM
            `tabEmployee` emp
        WHERE 
            emp.status != 'Left'
            {conditions}
        """
    return frappe.db.sql(sql, as_dict=True)
  
#customize: Lọc dữ liệu
def get_filter_conditions(filters):
    conditions = ""   
    if filters.get("employee"):
        conditions += " and emp.employee = '%s' " % (filters.get("employee"))
    if filters.get("company"):
        conditions += " and emp.company = '%s' " % (filters.get("company"))
    if filters.get("department"):
        conditions += " and emp.department = '%s' " % (filters.get("department"))
	if filters.get("type"):
		conditions += " and emp.department = '%s' " % (filters.get("department"))
    return conditions 

# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe


# apps/vinatex/vinatex/vnt_hr/report/danh_bạ_nội_bộ/danh_bạ_nội_bộ.py
from __future__ import unicode_literals
from frappe import _
import frappe

def execute(filters=None):
    filters = filters or {}
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data, None

def get_columns(filters=None):
    return [
        {"label": _("Số quyết định"), "fieldname": "decision_number", "fieldtype": "Data", "width": 150},
        {"label": _("Ngày hiệu lực"), "fieldname": "decision_number", "fieldtype": "Date", "width": 130},
       	{"label": _("Ngày ký"), "fieldname": "date_sign", "fieldtype": "Data", "width": 120},
        {"label": _("Trạng thái"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Người ký"), "fieldname": "signer_name", "fieldtype": "Data", "width": 170},
        {"label": _("Vị trí công việc người ký"), "fieldname": "position", "fieldtype": "Data", "width": 150},
        {"label": _("Chức danh người ký"), "fieldname": "desination", "fieldtype": "Data", "width": 140},
        {"label": _("Đối tượng khen thưởng"), "fieldname": "awardee", "fieldtype": "Data", "width": 160},
		{"label": _("Năm khen thưởng"), "fieldname": "year_awardee", "fieldtype": "Data", "width": 80},
    	{"label": _("Cơ quan/Đơn vị ra quyết định"), "fieldname": "issuing_authority", "fieldtype": "Data", "width": 200},
		{"label": _("Hình thức/Danh hiệu khen thưởng"), "fieldname": "reward_type", "fieldtype": "Data", "width": 200},
		{"label": _("Nội dung khen thưởng"), "fieldname": "decision_content", "fieldtype": "Data", "width": 200},
		{"label": _("Mức thưởng"), "fieldname": "reward_amount", "fieldtype": "Currency", "width": 200},
		{"label": _("Ghi chú"), "fieldname": "note", "fieldtype": "Data", "width": 200},
		{"label": _("Mã nhân viên"), "fieldname": "employee", "fieldtype": "Data", "width": 150},
		{"label": _("Họ tên"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		#{"label": _("Vị trí công việc"), "fieldname": "company_email", "fieldtype": "Data", "width": 200},
		{"label": _("Chức danh"), "fieldname": "cur_designation", "fieldtype": "Data", "width": 150},
		{"label": _("Bộ phận"), "fieldname": "cur_department", "fieldtype": "Data", "width": 200},
		{"label": _("Ngày phê duyệt"), "fieldname": "approver_date", "fieldtype": "Date", "width": 130},
		{"label": _("Người phê duyệt"), "fieldname": "approver_name", "fieldtype": "Data", "width": 150}
	]

def get_data(filters=None):
    where_sql, params = build_emp_conditions(filters)
    sql = f"""
        SELECT
            de.decision_number as decision_number,
			de.status as status,
			de.signer_name as signer_name,
			de.position as position,
			de.desination as desination,
			de.awardee as awardee,
			de.year_awardee as year_awardee,
			de.issuing_authority as issuing_authority,
			de.reward_type as reward_type,
			de.decision_content as decision_content,
			de.reward_amount as reward_amount,
			de.note as note,
			de.date_sign as date_sign,
			de_item.employee as employee,
			de_item.employee_name,
			de_item.cur_designation as cur_designation,
			de_item.cur_department as cur_department,
			de.approver_name as approver_name,
			de.approver_date as approver_date
        FROM `tabVNT Decision` de
		LEFT JOIN `tabVNT Decision Item` de_item ON de.name = de_item.parent
        WHERE de.docstatus < 2
        AND decision_type = 'Quyết định khen thưởng'
            {where_sql}
    """
    return frappe.db.sql(sql, params, as_dict=True)

def build_emp_conditions(filters=None):
    conds = []
    params = {}

    if filters.get("employee"):
        conds.append("AND de_item.employee = %(employee)s")   
        params["employee"] = filters["employee"]
    if filters.get("department"):
        conds.append("AND de_item.cur_department = %(department)s")
        params["department"] = filters["department"]

    where_sql = " ".join(conds)
    return where_sql, params


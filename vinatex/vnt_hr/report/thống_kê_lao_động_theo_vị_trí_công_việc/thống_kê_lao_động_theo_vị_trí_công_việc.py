# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters)
	summary = get_report_summary(data)

	# Trả về: columns, data, message(None), chart(None), report_summary
	return columns, data, None, None, summary


def get_columns():
	return [
		{"label": "Tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": "Ngày sinh", "fieldname": "date_of_birth", "fieldtype": "Date", "width": 110},
		{"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "options": "Department", "width": 180},
		{"label": "Vị trí công việc", "fieldname": "designation", "fieldtype": "Data", "options": "Designation", "width": 180},
		{"label": "Chi nhánh", "fieldname": "branch", "fieldtype": "Data", "options": "Branch", "width": 150},
		{"label": "Nhóm chức vụ", "fieldname": "custom_designation_group", "fieldtype": "Data", "options": "VNT Designation Group", "width": 160},
	]


def get_data(filters):
	conditions = []
	params = {}

	# Trạng thái: mặc định chỉ lấy Active
	status = (filters.get("status") or "Active").strip()
	if status and status != "Tất cả":
		conditions.append("e.status = %(status)s")
		params["status"] = status

	if filters.get("branch"):
		conditions.append("e.branch = %(branch)s")
		params["branch"] = filters.branch

	if filters.get("department"):
		conditions.append("e.department = %(department)s")
		params["department"] = filters.department

	if filters.get("designation"):
		conditions.append("e.designation = %(designation)s")
		params["designation"] = filters.designation

	if filters.get("designation_group"):
		conditions.append("e.custom_designation_group = %(designation_group)s")
		params["designation_group"] = filters.designation_group

	# Tìm nhanh: Mã NV / Tên / Vị trí công việc / Phòng ban
	if filters.get("search_text"):
		params["st"] = "%{0}%".format(filters.search_text.strip())
		conditions.append(
			"""(e.name LIKE %(st)s
				OR e.employee_name LIKE %(st)s
				OR e.designation LIKE %(st)s
				OR e.department LIKE %(st)s)"""
		)

	where = " AND ".join(conditions) if conditions else "1 = 1"

	sql = f"""
		SELECT
			e.name AS employee,
			e.employee_name,
			e.date_of_birth,
			e.department,
			e.designation,
			e.branch,
			e.custom_designation_group
		FROM `tabEmployee` e
		WHERE {where}
		ORDER BY
			IFNULL(e.designation, '') = '' ASC,
			e.designation ASC,
			e.department ASC,
			e.employee_name ASC
	"""

	return frappe.db.sql(sql, params, as_dict=True)


def get_report_summary(data):
	total = len(data)

	designations = {(row.get("designation") or "").strip() for row in data}
	designations.discard("")

	return [
		{"label": "Tổng lao động", "value": total, "indicator": "Blue", "datatype": "Int"},
		{"label": "Số vị trí công việc", "value": len(designations), "indicator": "Green", "datatype": "Int"},
	]

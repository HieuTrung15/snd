# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe import _

NO_DEPARTMENT = "(Không có phòng ban)"
MIDDLE_LEADER_GROUP = "Lãnh đạo cấp trung"


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_report_summary(data)

	# Trả về: columns, data, message(None), chart, report_summary
	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{"label": _("Phòng ban"), "fieldname": "department_name", "fieldtype": "Data", "width": 320},
		{"label": _("Viết tắt"), "fieldname": "short_name", "fieldtype": "Data", "width": 100},
		{"label": _("Tổng lao động"), "fieldname": "total", "fieldtype": "Int", "width": 120},
		{"label": _("Nam"), "fieldname": "male", "fieldtype": "Int", "width": 90},
		{"label": _("Nữ"), "fieldname": "female", "fieldtype": "Int", "width": 90},
		{"label": _("Số vị trí công việc"), "fieldname": "designation_count", "fieldtype": "Int", "width": 150},
		{"label": _("Lãnh đạo cấp trung"), "fieldname": "middle_leader", "fieldtype": "Int", "width": 160},
		{"label": _("Tuổi bình quân"), "fieldname": "avg_age", "fieldtype": "Float", "precision": 1, "width": 130},
	]


def get_data(filters):
	conditions = []
	params = {"no_dept": NO_DEPARTMENT, "middle_leader": MIDDLE_LEADER_GROUP}

	if filters.get("company"):
		conditions.append("e.company = %(company)s")
		params["company"] = filters.company

	# Trạng thái: mặc định chỉ lấy Active
	status = (filters.get("status") or "Active").strip()
	if status and status != "Tất cả":
		conditions.append("e.status = %(status)s")
		params["status"] = status

	if filters.get("department"):
		conditions.append("e.department = %(department)s")
		params["department"] = filters.department

	if filters.get("branch"):
		conditions.append("e.branch = %(branch)s")
		params["branch"] = filters.branch

	# Bỏ qua phòng ban đã bị vô hiệu hoá (giữ lại nhân sự chưa gán phòng ban)
	conditions.append("(d.name IS NULL OR d.disabled = 0)")

	where = " AND ".join(conditions)

	sql = f"""
		SELECT
			COALESCE(d.department_name, %(no_dept)s)            AS department_name,
			COALESCE(d.custom_short_name, '')                   AS short_name,
			COUNT(e.name)                                       AS total,
			SUM(CASE WHEN e.gender = 'Male' THEN 1 ELSE 0 END)  AS male,
			SUM(CASE WHEN e.gender = 'Female' THEN 1 ELSE 0 END) AS female,
			COUNT(DISTINCT NULLIF(e.designation, ''))           AS designation_count,
			SUM(CASE WHEN e.custom_designation_group = %(middle_leader)s THEN 1 ELSE 0 END) AS middle_leader,
			AVG(TIMESTAMPDIFF(YEAR, e.date_of_birth, CURDATE())) AS avg_age
		FROM `tabEmployee` e
		LEFT JOIN `tabDepartment` d ON e.department = d.name
		WHERE {where}
		GROUP BY department_name, short_name
		ORDER BY total DESC, department_name ASC
	"""

	rows = frappe.db.sql(sql, params, as_dict=True)

	return [
		{
			"department_name": r.department_name,
			"short_name": r.short_name or r.department_name,
			"total": int(r.total or 0),
			"male": int(r.male or 0),
			"female": int(r.female or 0),
			"designation_count": int(r.designation_count or 0),
			"middle_leader": int(r.middle_leader or 0),
			"avg_age": round(float(r.avg_age), 1) if r.avg_age is not None else 0.0,
		}
		for r in rows
	]


def get_chart(data):
	# Chỉ vẽ 10 phòng ban đông nhất
	top10 = data[:10]

	return {
		"data": {
			"labels": [d["short_name"] for d in top10],
			"datasets": [{"name": _("Lao động"), "values": [d["total"] for d in top10]}],
		},
		"type": "bar",
		"axis_options": {"x_axis_mode": "tick", "x_is_series": False},
		"height": 300,
	}


def get_report_summary(data):
	total_employees = sum(d["total"] for d in data)
	dept_count = len(data)
	avg_size = round(total_employees / dept_count, 2) if dept_count else 0.0
	max_row = max(data, key=lambda d: d["total"]) if data else None

	summary = [
		{"label": _("Tổng số lao động"), "value": total_employees, "indicator": "green", "datatype": "Int"},
		{"label": _("Tổng số phòng ban"), "value": dept_count, "indicator": "blue", "datatype": "Int"},
		{"label": _("Quy mô bình quân / phòng ban"), "value": avg_size, "datatype": "Float", "precision": 2},
	]

	if max_row:
		summary.append(
			{
				"label": _("Phòng ban nhiều lao động nhất"),
				"value": max_row["department_name"],
				"indicator": "blue",
				"datatype": "Data",
			}
		)

	return summary

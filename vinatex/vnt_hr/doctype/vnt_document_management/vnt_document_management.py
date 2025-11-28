# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document


class VNTDocumentManagement(Document):
	pass


@frappe.whitelist()
def get_level1_approvers():
	"""
	Return employees who are marked as level-1 approvers in Department.leave_approvers.
	Uses Department Approver.custom_level_1 to filter.
	"""
	# Fetch approver (user) entries that are flagged as level 1
	approver_rows = frappe.get_all(
		"Department Approver",
		filters={"parenttype": "Department", "custom_level_1": 1},
		fields=["approver"],
		distinct=True,
	)
	user_ids = {row.approver for row in approver_rows if row.approver}
	if not user_ids:
		return []

	# Map approver user_ids to Employee records
	employees = frappe.get_all(
		"Employee",
		filters={"user_id": ["in", list(user_ids)]},
		fields=["name", "employee_name", "department", "user_id"],
		distinct=True,
	)

	# Fallback: in case approver stores Employee name instead of User ID
	remaining_ids = user_ids - {emp.user_id for emp in employees if emp.user_id}
	if remaining_ids:
		extra = frappe.get_all(
			"Employee",
			filters={"name": ["in", list(remaining_ids)]},
			fields=["name", "employee_name", "department", "user_id"],
			distinct=True,
		)
		employees.extend(extra)

	seen = set()
	result = []
	for emp in employees:
		if emp.name in seen:
			continue
		seen.add(emp.name)
		result.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
			}
		)
	return result


@frappe.whitelist()
def filter_cv_xu_ly_by_collab(doctype, txt, searchfield, start, page_len, filters):
	"""
	Trả về nhân viên cùng phòng/ban với người phối hợp (nguoi_phoi_hop) trong bảng items2.
	"""
	collab = (filters or {}).get("nguoi_phoi_hop")
	if not collab:
		return []

	department = frappe.db.get_value("Employee", collab, "department")
	if not department:
		return []

	like_txt = f"%{txt or ''}%"
	rows = frappe.db.sql(
		"""
		SELECT name, employee_name
		FROM `tabEmployee`
		WHERE department = %(department)s
			AND (name LIKE %(txt)s OR employee_name LIKE %(txt)s)
		ORDER BY employee_name ASC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"department": department,
			"txt": like_txt,
			"page_len": page_len,
			"start": start,
		},
	)
	return rows

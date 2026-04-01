import frappe
from frappe.utils import flt, getdate, nowdate

from vinatex.vinatex.doctype.overrides.leave_application import get_leave_details_with_year

ANNUAL_LEAVE_TYPE = "Nghỉ phép năm"


def _get_active_employee_for_user(user: str | None = None):
	target_user = user or frappe.session.user
	if not target_user or target_user == "Guest":
		return None

	return frappe.db.get_value(
		"Employee",
		{"user_id": target_user, "status": "Active"},
		["name", "employee_name"],
		as_dict=True,
	)


def _extract_remaining_annual_leave(leave_allocation: dict | None, leave_type: str = ANNUAL_LEAVE_TYPE) -> float:
	total_remaining = 0.0
	yearly_prefix = f"{leave_type} ("

	for key, value in (leave_allocation or {}).items():
		if key == leave_type or (isinstance(key, str) and key.startswith(yearly_prefix)):
			total_remaining += flt((value or {}).get("remaining_leaves"))

	return flt(total_remaining)


def get_employee_remaining_annual_leave(employee: str, date=None, leave_type: str = ANNUAL_LEAVE_TYPE) -> dict:
	target_date = getdate(date or nowdate())
	if not employee:
		return {
			"employee": None,
			"leave_type": leave_type,
			"remaining": 0.0,
			"as_of_date": str(target_date),
		}

	leave_details = get_leave_details_with_year(employee, target_date, target_date)
	leave_allocation = leave_details.get("leave_allocation") or {}
	remaining = _extract_remaining_annual_leave(leave_allocation, leave_type)

	return {
		"employee": employee,
		"leave_type": leave_type,
		"remaining": remaining,
		"as_of_date": str(target_date),
	}


@frappe.whitelist()
def get_my_remaining_annual_leave(date=None):
	employee = _get_active_employee_for_user()
	target_date = getdate(date or nowdate())

	if not employee:
		return {
			"employee": None,
			"employee_name": None,
			"leave_type": ANNUAL_LEAVE_TYPE,
			"remaining": 0.0,
			"as_of_date": str(target_date),
		}

	result = get_employee_remaining_annual_leave(employee.name, target_date, ANNUAL_LEAVE_TYPE)
	result["employee_name"] = employee.employee_name
	return result

from __future__ import annotations

import frappe
from frappe import _


DOCTYPE = "VNT Organizational Structure"
ROOT_LABEL_PREFIX = "Chi nhánh Tập đoàn - "


def _display_heading(value: str | None) -> str:
	"""Keep the stored root intact while showing the single factory unit as the heading."""
	heading = (value or "").strip()
	if heading.casefold().startswith(ROOT_LABEL_PREFIX.casefold()):
		return heading[len(ROOT_LABEL_PREFIX) :].strip()
	return heading


@frappe.whitelist()
def get_chart_data():
	"""Return the active organizational units in Nested Set order."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)

	rows = frappe.get_list(
		DOCTYPE,
		filters={"disabled": 0},
		fields=[
			"name",
			"org_name",
			"parent_vnt_organizational_structure as parent",
			"is_group",
			"level",
			"lft",
			"rgt",
		],
		order_by="lft asc, org_name asc",
		limit_page_length=0,
	)

	return {
		"doctype": DOCTYPE,
		"total": len(rows),
		"heading": _display_heading(
			next((row.org_name or row.name for row in rows if not row.parent), "")
		),
		"nodes": [
			{
				"id": row.name,
				"name": row.org_name or row.name,
				"parent": row.parent or "",
				"is_group": bool(row.is_group),
				"level": row.level or "",
			}
			for row in rows
		],
		"message": _("Sơ đồ đã được cập nhật từ dữ liệu hiện tại"),
	}

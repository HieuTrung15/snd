"""Create the governed designation groups used by Employee."""

import frappe


DEFAULT_DESIGNATION_GROUPS = (
	"Lãnh đạo Chi nhánh",
	"Quản lý cấp trung",
	"Quản lý cấp cơ sở",
	"Nhân viên",
	"Công nhân",
)


def execute():
	for designation_group in DEFAULT_DESIGNATION_GROUPS:
		if frappe.db.exists("VNT Designation Group", designation_group):
			frappe.db.set_value(
				"VNT Designation Group",
				designation_group,
				"is_active",
				1,
				update_modified=False,
			)
			continue

		frappe.get_doc(
			{
				"doctype": "VNT Designation Group",
				"designation_group": designation_group,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)

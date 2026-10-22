"""Đưa Trưởng ca lên trên bốn công đoạn sản xuất và ẩn các nút không còn dùng."""

from __future__ import annotations

import frappe

from vinatex.patches.create_nam_dinh_organizational_structure import DOCTYPE


PRODUCTION = "Sản xuất trực tiếp"
SHIFT_LEAD = "Trưởng ca"
PRODUCTION_BRANCHES = (
	"Bông chải - Sản xuất",
	"Ghép thô - Sản xuất",
	"Máy con - Sản xuất",
	"Máy ống - Sản xuất",
)
OBSOLETE_NODES = ("Kỹ thuật", "Vào bông", "Nhặt bông")


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	for name in OBSOLETE_NODES:
		if frappe.db.exists(DOCTYPE, name):
			frappe.db.set_value(DOCTYPE, name, "disabled", 1, update_modified=False)

	if not frappe.db.exists(DOCTYPE, PRODUCTION):
		return

	if not frappe.db.exists(DOCTYPE, SHIFT_LEAD):
		frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"org_name": SHIFT_LEAD,
				"parent_vnt_organizational_structure": PRODUCTION,
				"is_group": 1,
				"disabled": 0,
				"level": "Quản lý",
			}
		).insert(ignore_permissions=True)
	else:
		_move_node(SHIFT_LEAD, PRODUCTION, is_group=1, level="Quản lý")

	for branch in PRODUCTION_BRANCHES:
		if frappe.db.exists(DOCTYPE, branch):
			_move_node(branch, SHIFT_LEAD)

	frappe.db.set_value(DOCTYPE, PRODUCTION, "is_group", 1, update_modified=False)


def _move_node(name, parent, *, is_group=None, level=None):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.parent_vnt_organizational_structure = parent
	doc.disabled = 0
	if is_group is not None:
		doc.is_group = is_group
	if level is not None:
		doc.level = level
	doc.save(ignore_permissions=True)

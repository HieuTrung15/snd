"""Bổ sung các cấp chức danh vận hành vào sơ đồ tổ chức Nhà máy Sợi Nam Định."""

from __future__ import annotations

import frappe

from vinatex.patches.create_nam_dinh_organizational_structure import DOCTYPE, NODES


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	existing = set(frappe.get_all(DOCTYPE, pluck="name"))
	for name, parent, level in NODES:
		if name in existing:
			continue
		if parent and parent not in existing:
			continue

		if parent:
			frappe.db.set_value(DOCTYPE, parent, "is_group", 1, update_modified=False)

		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"org_name": name,
				"parent_vnt_organizational_structure": parent or None,
				"is_group": 0,
				"disabled": 0,
				"level": level,
			}
		)
		doc.insert(ignore_permissions=True)
		existing.add(name)

	parents = {parent for _name, parent, _level in NODES if parent}
	for parent in parents.intersection(existing):
		frappe.db.set_value(DOCTYPE, parent, "is_group", 1, update_modified=False)

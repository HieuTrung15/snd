# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

import frappe


def execute():
	_migrate_link_column_to_child_table(
		parent_doctype="VNT Document Management",
		child_doctype="VNT Document Management Incoming Link",
		parent_field="vnt_doc_mng",
		child_link_field="incoming_document",
	)
	_migrate_link_column_to_child_table(
		parent_doctype="VNT Document Management",
		child_doctype="VNT Document Management Outgoing Link",
		parent_field="cong_van_di",
		child_link_field="outgoing_document",
	)


def _migrate_link_column_to_child_table(
	*,
	parent_doctype: str,
	child_doctype: str,
	parent_field: str,
	child_link_field: str,
):
	if not frappe.db.table_exists(parent_doctype) or not frappe.db.table_exists(child_doctype):
		return

	if not frappe.db.has_column(parent_doctype, parent_field):
		return

	source_rows = frappe.db.sql(
		f"""
		select
			name,
			`{parent_field}` as link_name
		from `tab{parent_doctype}`
		where ifnull(`{parent_field}`, '') != ''
		""",
		as_dict=True,
	)
	if not source_rows:
		return

	existing_rows = frappe.db.sql(
		f"""
		select
			parent,
			idx,
			`{child_link_field}` as link_name
		from `tab{child_doctype}`
		where parenttype = %s and parentfield = %s
		""",
		(parent_doctype, parent_field),
		as_dict=True,
	)

	existing_pairs: set[tuple[str, str]] = set()
	idx_by_parent: dict[str, int] = {}
	for row in existing_rows:
		parent = row.get("parent")
		if not parent:
			continue
		idx_value = row.get("idx") or 0
		try:
			idx = int(idx_value)
		except Exception:
			idx = 0
		idx_by_parent[parent] = max(idx_by_parent.get(parent, 0), idx)

		link_name = (row.get("link_name") or "").strip()
		if link_name:
			existing_pairs.add((parent, link_name))

	for row in source_rows:
		parent = row.get("name")
		link_name = (row.get("link_name") or "").strip()
		if not parent or not link_name:
			continue

		pair = (parent, link_name)
		if pair in existing_pairs:
			continue

		next_idx = idx_by_parent.get(parent, 0) + 1
		idx_by_parent[parent] = next_idx
		existing_pairs.add(pair)

		frappe.db.sql(
			f"""
			insert into `tab{child_doctype}`
				(name, creation, modified, modified_by, owner, docstatus, idx, parent, parentfield, parenttype, `{child_link_field}`)
			values
				(%s, now(), now(), %s, %s, 0, %s, %s, %s, %s, %s)
			""",
			(
				frappe.generate_hash(length=10),
				"Administrator",
				"Administrator",
				next_idx,
				parent,
				parent_field,
				parent_doctype,
				link_name,
			),
		)

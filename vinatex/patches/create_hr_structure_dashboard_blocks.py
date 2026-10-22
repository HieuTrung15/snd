"""Create workforce-structure blocks and attach them to the HR workspace."""

import json

import frappe

from vinatex.vnt_hr.custom_html_block.sync import sync_block


WORKSPACE_NAME = "Quản trị nhân sự"
BLOCKS = (
	(
		"Cơ cấu NLĐ theo nhóm chức danh - Donut",
		"designation_group_structure",
		"VNTDESGROUP1",
	),
	(
		"Cơ cấu NLĐ theo phòng bộ phận - Thanh ngang",
		"department_structure",
		"VNTDEPARTMENT1",
	),
)


def execute():
	for name, folder, _block_id in BLOCKS:
		sync_block(name, folder)

	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	workspace = frappe.get_doc("Workspace", WORKSPACE_NAME)
	content = frappe.parse_json(workspace.content or "[]") or []
	existing_content_names = {
		item.get("data", {}).get("custom_block_name")
		for item in content
		if item.get("type") == "custom_block"
	}

	for name, _folder, block_id in BLOCKS:
		if name not in existing_content_names:
			content.append(
				{
					"id": block_id,
					"type": "custom_block",
					"data": {"custom_block_name": name, "col": 6},
				}
			)

	workspace.content = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
	existing_child_names = {row.custom_block_name for row in workspace.custom_blocks}
	for name, _folder, _block_id in BLOCKS:
		if name not in existing_child_names:
			workspace.append("custom_blocks", {"custom_block_name": name, "label": name})

	workspace.save(ignore_permissions=True)

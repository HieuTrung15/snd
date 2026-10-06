"""Install the consolidated Home dashboard block and attach it to Home."""

import json

import frappe

from vinatex.vnt_hr.custom_html_block.sync import sync_all


BLOCK_NAME = "Trang chủ tổng hợp"


def execute():
	sync_all()

	if not frappe.db.exists("Workspace", "Home"):
		return

	workspace = frappe.get_doc("Workspace", "Home")
	workspace.content = json.dumps(
		[
			{
				"id": "VNTHOMEDASHBOARD",
				"type": "custom_block",
				"data": {"custom_block_name": BLOCK_NAME, "col": 12},
			}
		],
		ensure_ascii=False,
		separators=(",", ":"),
	)
	workspace.set(
		"custom_blocks",
		[{"custom_block_name": BLOCK_NAME, "label": BLOCK_NAME}],
	)
	workspace.save(ignore_permissions=True)
	frappe.db.commit()

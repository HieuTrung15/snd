"""Khởi tạo sơ đồ tổ chức Nhà máy Sợi Vinatex Nam Định khi danh mục còn trống."""

from __future__ import annotations

import frappe


DOCTYPE = "VNT Organizational Structure"
ROOT = "Chi nhánh Tập đoàn - Nhà máy Sợi Vinatex Nam Định"
WORKSPACE = "1.1 Tổ chức"
WORKSPACE_SHORTCUT = "Sơ đồ tổ chức"

# Thứ tự cha trước con để NestedSet có thể cập nhật lft/rgt ngay khi chèn.
BASE_NODES = (
	(ROOT, "", "Quản lý"),
	("Ban Giám đốc", ROOT, "Quản lý"),
	("Giám đốc chi nhánh", "Ban Giám đốc", "Quản lý"),
	("Phó Giám đốc chi nhánh", "Ban Giám đốc", "Quản lý"),
	("Phòng TCKT", ROOT, "Quản lý"),
	("Kế toán", "Phòng TCKT", "Trực thuộc"),
	("Phòng HCNS", ROOT, "Quản lý"),
	("Nhân sự", "Phòng HCNS", "Trực thuộc"),
	("Lái xe", "Phòng HCNS", "Trực thuộc"),
	("Nhà ăn", "Phòng HCNS", "Trực thuộc"),
	("Phòng ĐHSX", ROOT, "Quản lý"),
	("Bảo toàn / Bảo trì", "Phòng ĐHSX", "Quản lý"),
	("Bông chải - Bảo toàn", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Ghép thô - Bảo toàn", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Máy con - Bảo toàn", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Máy ống - Bảo toàn", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Thí nghiệm", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Điều không", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Điện", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Đóng gói", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Suốt da", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Cơ khí", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("VSCN", "Bảo toàn / Bảo trì", "Trực thuộc"),
	("Sản xuất trực tiếp", "Phòng ĐHSX", "Quản lý"),
	("Trưởng ca", "Sản xuất trực tiếp", "Quản lý"),
	("Bông chải - Sản xuất", "Trưởng ca", "Trực thuộc"),
	("Ghép thô - Sản xuất", "Trưởng ca", "Trực thuộc"),
	("Máy con - Sản xuất", "Trưởng ca", "Trực thuộc"),
	("Máy ống - Sản xuất", "Trưởng ca", "Trực thuộc"),
	("Phòng Kinh doanh", ROOT, "Quản lý"),
)

MAINTENANCE_ROLE_BRANCHES = (
	"Bông chải - Bảo toàn",
	"Ghép thô - Bảo toàn",
	"Máy con - Bảo toàn",
	"Máy ống - Bảo toàn",
	"Thí nghiệm",
	"Điều không",
	"Điện",
	"Đóng gói",
	"Suốt da",
	"Cơ khí",
)
PRODUCTION_ROLE_BRANCHES = (
	"Bông chải - Sản xuất",
	"Ghép thô - Sản xuất",
	"Máy con - Sản xuất",
	"Máy ống - Sản xuất",
)


def _role_nodes():
	nodes = []
	for branch in MAINTENANCE_ROLE_BRANCHES:
		short_name = branch.split(" - ", 1)[0]
		lead = f"Trưởng CĐ - {short_name}"
		deputy = f"Phó trưởng CĐ - {short_name}"
		nodes.extend(
			(
				(lead, branch, "Trực thuộc"),
				(deputy, lead, "Trực thuộc"),
				(f"CN bảo toàn - {short_name}", deputy, "Trực thuộc"),
			)
		)

	nodes.append(("CN công nghệ - VSCN", "VSCN", "Trực thuộc"))

	for branch in PRODUCTION_ROLE_BRANCHES:
		short_name = branch.split(" - ", 1)[0]
		lead = f"Tổ trưởng SX - {short_name}"
		deputy = f"Tổ phó SX - {short_name}"
		nodes.extend(
			(
				(lead, branch, "Trực thuộc"),
				(deputy, lead, "Trực thuộc"),
				(f"CN công nghệ - {short_name}", deputy, "Trực thuộc"),
			)
		)
	return nodes


NODES = BASE_NODES + tuple(_role_nodes())


def execute():
	if not frappe.db.count(DOCTYPE):
		parents = {parent for _name, parent, _level in NODES if parent}
		for name, parent, level in NODES:
			doc = frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"org_name": name,
					"parent_vnt_organizational_structure": parent or None,
					"is_group": int(name in parents),
					"disabled": 0,
					"level": level,
				}
			)
			doc.insert(ignore_permissions=True)

	_update_workspace_shortcut()


def _update_workspace_shortcut():
	"""Open the organization chart page directly from the existing workspace tile."""
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	workspace = frappe.get_doc("Workspace", WORKSPACE)
	for shortcut in workspace.shortcuts:
		if shortcut.label == WORKSPACE_SHORTCUT:
			shortcut.type = "Page"
			shortcut.link_to = "vnt-organization-chart"
			shortcut.doc_view = None
			workspace.save(ignore_permissions=True)
			return

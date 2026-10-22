from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.patches.create_nam_dinh_organizational_structure import NODES, ROOT
from vinatex.vnt_hr.page.vnt_organization_chart.vnt_organization_chart import (
	_display_heading,
	get_chart_data,
)


class TestVNTOrganizationChart(TestCase):
	def test_nam_dinh_seed_has_unique_nodes_and_valid_parent_order(self):
		seen = set()
		for name, parent, _level in NODES:
			self.assertNotIn(name, seen)
			if parent:
				self.assertIn(parent, seen)
			seen.add(name)

		self.assertEqual(NODES[0][:2], (ROOT, ""))
		self.assertEqual(len(seen), 73)
		self.assertNotIn("Kỹ thuật", seen)
		self.assertNotIn("Vào bông", seen)
		self.assertNotIn("Nhặt bông", seen)

		parent_by_name = {name: parent for name, parent, _level in NODES}
		self.assertEqual(parent_by_name["Trưởng CĐ - Bông chải"], "Bông chải - Bảo toàn")
		self.assertEqual(parent_by_name["Phó trưởng CĐ - Bông chải"], "Trưởng CĐ - Bông chải")
		self.assertEqual(parent_by_name["CN bảo toàn - Bông chải"], "Phó trưởng CĐ - Bông chải")
		self.assertEqual(parent_by_name["Tổ trưởng SX - Máy con"], "Máy con - Sản xuất")
		self.assertEqual(parent_by_name["Tổ phó SX - Máy con"], "Tổ trưởng SX - Máy con")
		self.assertEqual(parent_by_name["CN công nghệ - Máy con"], "Tổ phó SX - Máy con")
		self.assertEqual(parent_by_name["Trưởng ca"], "Sản xuất trực tiếp")
		for branch in (
			"Bông chải - Sản xuất",
			"Ghép thô - Sản xuất",
			"Máy con - Sản xuất",
			"Máy ống - Sản xuất",
		):
			self.assertEqual(parent_by_name[branch], "Trưởng ca")

	def test_root_heading_shows_only_the_factory_unit(self):
		self.assertEqual(
			_display_heading("Chi nhánh Tập đoàn - Nhà máy Sợi Vinatex Nam Định"),
			"Nhà máy Sợi Vinatex Nam Định",
		)

	@patch("vinatex.vnt_hr.page.vnt_organization_chart.vnt_organization_chart.frappe")
	def test_get_chart_data_preserves_nested_set_order_and_root_heading(self, mock_frappe):
		mock_frappe.get_list.return_value = [
			frappe._dict(
				name="Nhà máy Sợi Vinatex Nam Định",
				org_name="Nhà máy Sợi Vinatex Nam Định",
				parent="",
				is_group=1,
				level="Quản lý",
				lft=1,
				rgt=4,
			),
			frappe._dict(
				name="Phòng Điều hành sản xuất",
				org_name="Phòng Điều hành sản xuất",
				parent="Nhà máy Sợi Vinatex Nam Định",
				is_group=0,
				level="Trực thuộc",
				lft=2,
				rgt=3,
			),
		]

		with patch(
			"vinatex.vnt_hr.page.vnt_organization_chart.vnt_organization_chart._",
			side_effect=lambda message: message,
		):
			result = get_chart_data.__wrapped__()

		mock_frappe.has_permission.assert_called_once_with(
			"VNT Organizational Structure", ptype="read", throw=True
		)
		self.assertEqual(result["total"], 2)
		self.assertEqual(result["heading"], "Nhà máy Sợi Vinatex Nam Định")
		self.assertEqual(result["nodes"][1]["parent"], "Nhà máy Sợi Vinatex Nam Định")
		self.assertEqual(result["nodes"][1]["level"], "Trực thuộc")

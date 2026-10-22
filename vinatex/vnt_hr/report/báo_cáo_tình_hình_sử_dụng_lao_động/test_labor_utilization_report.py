from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from vinatex.vnt_hr.report.báo_cáo_tình_hình_sử_dụng_lao_động.báo_cáo_tình_hình_sử_dụng_lao_động import (
	LABOR_FIELDS,
	_make_workbook,
	get_data,
)


class TestLaborUtilizationWorkbook(TestCase):
	def get_report_rows(self, database_rows):
		db = MagicMock()
		db.sql.return_value = database_rows

		def parse_date(value=None):
			return date.fromisoformat(value) if value else date(2026, 10, 20)

		with (
			patch.dict(frappe.__dict__, {"db": db}),
			patch(f"{get_data.__module__}.getdate", side_effect=parse_date),
		):
			rows = get_data(
				{
					"company": "Nhà máy Sợi Vinatex Nam Định",
					"from_date": "2026-10-01",
					"to_date": "2026-10-31",
				}
			)
		return rows, db

	def test_get_data_only_queries_active_employees_in_enabled_departments(self):
		rows, db = self.get_report_rows(
			[{"department": "Phòng Nhân sự", "department_name": "Phòng Nhân sự"}]
		)

		query = " ".join(db.sql.call_args.args[0].split())
		self.assertIn("e.status = 'Active'", query)
		self.assertIn("d.disabled = 0", query)
		self.assertIn("sp.docstatus = 1", query)
		self.assertIn("SUM(spd.number_of_positions)", query)
		self.assertEqual(db.sql.call_count, 1)
		self.assertEqual([row["department_name"] for row in rows], ["Phòng Nhân sự"])
		self.assertIsNone(rows[0]["annual_labor_plan"])
		self.assertIsNone(rows[0]["plan_achievement_pct"])
		self.assertIsNone(rows[0]["plan_variance"])
		query_values = db.sql.call_args.args[1]
		self.assertEqual(query_values["plan_from_date"], date(2026, 1, 1))
		self.assertEqual(query_values["plan_to_date"], date(2026, 12, 31))

	def test_get_data_calculates_annual_plan_comparison(self):
		rows, _db = self.get_report_rows(
			[
				{
					"department": "Phòng Nhân sự",
					"department_name": "Phòng Nhân sự",
					"end_total": 15,
					"annual_labor_plan": 12,
				}
			]
		)

		self.assertEqual(rows[0]["annual_labor_plan"], 12)
		self.assertEqual(rows[0]["plan_achievement_pct"], 125)
		self.assertEqual(rows[0]["plan_variance"], 3)

	def test_workbook_preserves_grouped_report_header_and_totals(self):
		row = {fieldname: 1 for fieldname in LABOR_FIELDS}
		row.update(
			{
				"stt": 1,
				"department_name": "Phòng Nhân sự",
				"annual_labor_plan": 2,
				"plan_achievement_pct": 50,
				"plan_variance": -1,
			}
		)
		workbook = _make_workbook(
			"Nhà máy Sợi Vinatex Nam Định",
			date(2026, 10, 1),
			date(2026, 10, 31),
			[row],
		)
		worksheet = workbook.active

		self.assertIn("C7:R7", {str(cell_range) for cell_range in worksheet.merged_cells.ranges})
		self.assertIn("S7:U7", {str(cell_range) for cell_range in worksheet.merged_cells.ranges})
		self.assertIn("T8:U8", {str(cell_range) for cell_range in worksheet.merged_cells.ranges})
		self.assertEqual(worksheet["A4"].value, "BÁO CÁO TÌNH HÌNH SỬ DỤNG LAO ĐỘNG")
		self.assertEqual(worksheet["N10"].value, "Không xác định thời hạn")
		self.assertEqual(worksheet["S8"].value, "LĐ kế hoạch năm")
		self.assertEqual(worksheet["B11"].value, "Phòng Nhân sự")
		self.assertEqual(worksheet["S11"].value, 2)
		self.assertEqual(worksheet["T11"].value, 0.5)
		self.assertEqual(worksheet["U11"].value, -1)
		self.assertEqual(worksheet["B12"].value, "TỔNG CỘNG")
		self.assertEqual(worksheet["R12"].value, 1)
		self.assertEqual(worksheet["S12"].value, 2)
		self.assertEqual(worksheet["T12"].value, 0.5)
		self.assertEqual(worksheet["U12"].value, -1)

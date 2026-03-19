# Copyright (c) 2026, vinatex and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from vinatex.vnt_itsec.sync.cvelistv5 import _build_resume_cursor, _parse_resume_cursor


class TestCvelistV5Sync(FrappeTestCase):
	def test_resume_cursor_round_trip(self):
		cursor = _build_resume_cursor(
			mode="DIFF",
			base_rev="abc123",
			target_rev="def456",
			next_index=42,
		)
		parsed = _parse_resume_cursor(cursor)
		self.assertIsNotNone(parsed)
		self.assertEqual(parsed.get("mode"), "DIFF")
		self.assertEqual(parsed.get("base_rev"), "abc123")
		self.assertEqual(parsed.get("target_rev"), "def456")
		self.assertEqual(parsed.get("next_index"), 42)

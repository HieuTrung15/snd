# Copyright (c) 2026, vinatex and Contributors
# See license.txt

from types import SimpleNamespace

from frappe.tests.utils import FrappeTestCase

from vinatex.vnt_itsec.matching.match import (
	_compare_versions,
	_component_context,
	_matching_cves_for_component,
	_version_matches,
)


class TestITSecMatch(FrappeTestCase):
	def test_compare_versions_handles_numeric_and_prerelease(self):
		self.assertEqual(_compare_versions("15.0.1", "15.0.1"), 0)
		self.assertGreater(_compare_versions("15.0.10", "15.0.2"), 0)
		self.assertGreater(_compare_versions("7.4.4", "7.4"), 0)
		self.assertGreater(_compare_versions("1.0", "1.0rc1"), 0)
		self.assertLess(_compare_versions("1.0b1", "1.0"), 0)

	def test_version_matches_respects_including_and_excluding_bounds(self):
		component = {"version": "15.0.1"}
		self.assertTrue(
			_version_matches(
				component,
				{
					"cpe_name": "cpe:2.3:a:frappe:frappe:*:*:*:*:*:*:*:*",
					"version_start_including": "14.0.0",
					"version_end_excluding": "15.1.0",
				},
			)
		)
		self.assertFalse(
			_version_matches(
				component,
				{
					"cpe_name": "cpe:2.3:a:frappe:frappe:*:*:*:*:*:*:*:*",
					"version_start_excluding": "15.0.1",
				},
			)
		)
		self.assertFalse(
			_version_matches(
				component,
				{
					"cpe_name": "cpe:2.3:a:frappe:frappe:*:*:*:*:*:*:*:*",
					"version_end_including": "15.0.0",
				},
			)
		)

	def test_matching_cves_for_component_deduplicates_same_cve(self):
		component_ctx = _component_context(
			SimpleNamespace(
				cpe_name="cpe:2.3:a:frappe:frappe_framework:15.0.1:*:*:*:*:*:*:*",
				vendor="",
				product="",
				version="15.0.1",
			)
		)
		indexed = {
			("frappe", "frappe_framework"): [
				{
					"cve": "CVE-2026-0001",
					"cpe_name": "cpe:2.3:a:frappe:frappe_framework:*:*:*:*:*:*:*:*",
					"version_start_including": "14.0.0",
					"version_end_excluding": "16.0.0",
				},
				{
					"cve": "CVE-2026-0001",
					"cpe_name": "cpe:2.3:a:frappe:frappe_framework:15.0.1:*:*:*:*:*:*:*",
					"version_start_including": "",
					"version_end_excluding": "",
				},
			]
		}
		matches = _matching_cves_for_component(component_ctx, indexed)
		self.assertEqual(len(matches), 1)
		self.assertEqual(matches[0]["cve"], "CVE-2026-0001")
		self.assertEqual(matches[0]["match_confidence"], "High")

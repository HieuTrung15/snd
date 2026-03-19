# Copyright (c) 2026, vinatex and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from vinatex.vnt_it_security.doctype.vnt_it_asset.vnt_it_asset import (
	_build_cpe_name,
	_normalize_cpe_fragment,
	_pick_best_cpe,
)


class TestVNTITAsset(FrappeTestCase):
	def test_build_cpe_name_with_placeholder(self):
		cpe = _build_cpe_name(
			"cpe:2.3:a:vendor:product:{version}:*:*:*:*:*:*:*",
			"1.2.3",
		)
		self.assertEqual(cpe, "cpe:2.3:a:vendor:product:1.2.3:*:*:*:*:*:*:*")

	def test_build_cpe_name_replace_wildcard_version(self):
		cpe = _build_cpe_name(
			"cpe:2.3:a:vendor:product:*:*:*:*:*:*:*:*",
			"9.9.9",
		)
		self.assertEqual(cpe, "cpe:2.3:a:vendor:product:9.9.9:*:*:*:*:*:*:*")

	def test_normalize_cpe_fragment(self):
		self.assertEqual(_normalize_cpe_fragment("Cisco Systems, Inc"), "cisco_systems_inc")
		self.assertEqual(_normalize_cpe_fragment("Air-Flow"), "air-flow")

	def test_pick_best_cpe_prefers_exact_version(self):
		cpe = _pick_best_cpe(
			[
				"cpe:2.3:a:apache:airflow:*:*:*:*:*:*:*:*",
				"cpe:2.3:a:apache:airflow:2.8.3:*:*:*:*:*:*:*",
			],
			vendor_name="apache",
			product_name="airflow",
			version="2.8.3",
		)
		self.assertEqual(cpe, "cpe:2.3:a:apache:airflow:2.8.3:*:*:*:*:*:*:*")

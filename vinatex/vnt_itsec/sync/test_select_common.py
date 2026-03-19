# Copyright (c) 2026, vinatex and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from vinatex.vnt_itsec.sync.common import normalize_select_key, select_value, select_values


class TestSelectCommon(FrappeTestCase):
    def test_normalize_select_key(self):
        self.assertEqual(normalize_select_key("Critical"), "Critical")
        self.assertEqual(normalize_select_key(" Critical "), "Critical")
        self.assertEqual(normalize_select_key(""), "")

    def test_select_value_and_select_values(self):
        mapped = select_value("VNT CVE", "severity", "Critical")
        self.assertEqual(normalize_select_key(mapped), "Critical")

        values = select_values("VNT CVE", "severity", ["Critical"])
        self.assertIn("Critical", values)

# Copyright (c) 2026, vinatex and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from vinatex.vnt_it_security.doctype.vnt_remediation_ticket.vnt_remediation_ticket import (
	_affected_status_from_ticket_status,
	_priority_from_severity,
)


class TestVNTRemediationTicket(FrappeTestCase):
	def test_priority_from_severity(self):
		self.assertEqual(_priority_from_severity("Critical"), "P1")
		self.assertEqual(_priority_from_severity("High"), "P2")
		self.assertEqual(_priority_from_severity("Medium"), "P3")
		self.assertEqual(_priority_from_severity("Low"), "P4")
		self.assertEqual(_priority_from_severity(""), "P4")

	def test_affected_status_from_ticket_status(self):
		self.assertEqual(_affected_status_from_ticket_status("Done"), "Mitigated")
		self.assertEqual(_affected_status_from_ticket_status("Rejected"), "Accepted Risk")
		self.assertIsNone(_affected_status_from_ticket_status("Open"))
		self.assertIsNone(_affected_status_from_ticket_status(""))

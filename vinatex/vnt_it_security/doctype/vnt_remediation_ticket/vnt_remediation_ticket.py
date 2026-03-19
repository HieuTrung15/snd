# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime, nowdate

from vinatex.vnt_itsec.sync.common import normalize_select_key, select_value


class VNTRemediationTicket(Document):
	def validate(self):
		self._set_defaults()
		self._set_closed_at()

	def _set_defaults(self):
		if not self.status:
			self.status = select_value("VNT Remediation Ticket", "status", "Open")

		if self.asset and not self.company:
			self.company = frappe.db.get_value("VNT IT Asset", self.asset, "company")

		if self.asset and not self.assignee:
			service_owner = frappe.db.get_value("VNT IT Asset", self.asset, "service_owner")
			if service_owner and frappe.db.exists("User", service_owner):
				self.assignee = service_owner

		if not self.assignee:
			self.assignee = "Administrator"

		if not self.priority and self.cve:
			severity = frappe.db.get_value("VNT CVE", self.cve, "severity") or "Unknown"
			self.priority = select_value(
				"VNT Remediation Ticket", "priority", _priority_from_severity(severity)
			)

		if not self.priority:
			self.priority = select_value("VNT Remediation Ticket", "priority", "P3")

		if not self.sla_due_date:
			sla_days = 7
			if self.advisory:
				sla_days = int(
					frappe.db.get_value("VNT Vulnerability Advisory", self.advisory, "sla_days")
					or sla_days
				)
			self.sla_due_date = add_days(nowdate(), sla_days)

	def _set_closed_at(self):
		closed_statuses = {"Done", "Rejected"}
		current_status = normalize_select_key(self.status)
		if current_status in closed_statuses and not self.closed_at:
			self.closed_at = now_datetime()
		if current_status not in closed_statuses:
			self.closed_at = None


def _priority_from_severity(severity: str) -> str:
	normalized = normalize_select_key(severity) or "Unknown"
	if normalized == "Critical":
		return "P1"
	if normalized == "High":
		return "P2"
	if normalized == "Medium":
		return "P3"
	return "P4"

# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime, nowdate

from vinatex.vnt_itsec.sync.common import normalize_select_key, select_value, select_values


_CLOSED_TICKET_STATUS_KEYS = ("Done", "Rejected")
_OPEN_AFFECTED_STATUS_KEYS = ("Open", "In Progress")
_TICKET_TO_AFFECTED_STATUS = {
	"Done": "Mitigated",
	"Rejected": "Accepted Risk",
}


class VNTRemediationTicket(Document):
	def validate(self):
		self._set_defaults()
		self._set_closed_at()

	def on_update(self):
		affected_advisories = self._sync_related_affected_assets()
		self._close_resolved_advisories(affected_advisories)

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
		current_status = normalize_select_key(self.status)
		if current_status in _CLOSED_TICKET_STATUS_KEYS and not self.closed_at:
			self.closed_at = now_datetime()
		if current_status not in _CLOSED_TICKET_STATUS_KEYS:
			self.closed_at = None

	def _sync_related_affected_assets(self) -> set[str]:
		target_status = _affected_status_from_ticket_status(self.status)
		if not target_status or not self.asset or not self.cve:
			return set()

		open_statuses = select_values("VNT Affected Asset", "status", _OPEN_AFFECTED_STATUS_KEYS)
		rows = frappe.get_all(
			"VNT Affected Asset",
			filters={
				"asset": self.asset,
				"cve": self.cve,
				"status": ["in", open_statuses],
			},
			fields=["name", "advisory"],
		)
		if not rows:
			return set()

		resolved_status = select_value("VNT Affected Asset", "status", target_status)
		timestamp = now_datetime()
		advisories: set[str] = set()
		for row in rows:
			frappe.db.set_value(
				"VNT Affected Asset",
				row.name,
				{
					"status": resolved_status,
					"last_update": timestamp,
				},
				update_modified=True,
			)
			if row.advisory:
				advisories.add(row.advisory)
		return advisories

	def _close_resolved_advisories(self, advisory_names: set[str]) -> None:
		candidates = set(advisory_names or set())
		if self.advisory:
			candidates.add(self.advisory)
		for advisory_name in sorted(name for name in candidates if name):
			_close_advisory_if_resolved(advisory_name)


def _priority_from_severity(severity: str) -> str:
	normalized = normalize_select_key(severity) or "Unknown"
	if normalized == "Critical":
		return "P1"
	if normalized == "High":
		return "P2"
	if normalized == "Medium":
		return "P3"
	return "P4"


def _affected_status_from_ticket_status(ticket_status: str | None) -> str | None:
	return _TICKET_TO_AFFECTED_STATUS.get(normalize_select_key(ticket_status))


def _close_advisory_if_resolved(advisory_name: str) -> None:
	if not advisory_name:
		return

	advisory = frappe.get_value("VNT Vulnerability Advisory", advisory_name, ["name", "status"], as_dict=True)
	if not advisory or normalize_select_key(advisory.status) == "Closed":
		return

	open_affected_statuses = select_values("VNT Affected Asset", "status", _OPEN_AFFECTED_STATUS_KEYS)
	closed_ticket_statuses = select_values(
		"VNT Remediation Ticket",
		"status",
		_CLOSED_TICKET_STATUS_KEYS,
	)
	has_open_affected = frappe.db.exists(
		"VNT Affected Asset",
		{
			"advisory": advisory_name,
			"status": ["in", open_affected_statuses],
		},
	)
	has_open_tickets = frappe.db.exists(
		"VNT Remediation Ticket",
		{
			"advisory": advisory_name,
			"status": ["not in", closed_ticket_statuses],
		},
	)
	if has_open_affected or has_open_tickets:
		return

	frappe.db.set_value(
		"VNT Vulnerability Advisory",
		advisory_name,
		"status",
		select_value("VNT Vulnerability Advisory", "status", "Closed"),
		update_modified=True,
	)

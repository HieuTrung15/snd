# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from vinatex.vnt_itsec.automation import ensure_remediation_ticket_for_affected_asset
from vinatex.vnt_itsec.sync.common import select_value


def _normalize_component_row_id(value: str | None) -> str:
	return (value or "").strip()


def _existing_global_duplicate(doc: "VNTAffectedAsset") -> str | None:
	if not doc.asset or not doc.cve:
		return None
	rows = frappe.get_all(
		"VNT Affected Asset",
		filters={
			"asset": doc.asset,
			"cve": doc.cve,
			"component_row_id": _normalize_component_row_id(doc.component_row_id),
		},
		fields=["name"],
		limit=2,
	)
	for row in rows:
		if row.name != doc.name:
			return row.name
	return None


class VNTAffectedAsset(Document):
	def validate(self):
		self.component_row_id = _normalize_component_row_id(self.component_row_id)
		if not self.status:
			self.status = select_value("VNT Affected Asset", "status", "Open")
		duplicate_name = _existing_global_duplicate(self)
		if duplicate_name:
			frappe.throw(
				_("Affected asset already exists for this asset/CVE/component: {0}").format(
					duplicate_name
				),
				frappe.DuplicateEntryError,
			)
		self.last_update = now_datetime()

	def after_insert(self):
		try:
			ensure_remediation_ticket_for_affected_asset(self.name, commit=0)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Auto ticket creation failed for affected asset {self.name}",
			)

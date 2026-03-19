# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from vinatex.vnt_itsec.automation import ensure_remediation_ticket_for_affected_asset
from vinatex.vnt_itsec.sync.common import select_value

class VNTAffectedAsset(Document):
	def validate(self):
		if not self.status:
			self.status = select_value("VNT Affected Asset", "status", "Open")
		self.last_update = now_datetime()

	def after_insert(self):
		try:
			ensure_remediation_ticket_for_affected_asset(self.name, commit=0)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Auto ticket creation failed for affected asset {self.name}",
			)

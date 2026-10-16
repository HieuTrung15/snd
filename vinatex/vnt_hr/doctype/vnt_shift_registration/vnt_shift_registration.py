# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

KIP_TIME_MAP = {
	"Sáng (06:00-14:00)": ("06:00:00", "14:00:00"),
	"Chiều (14:00-22:00)": ("14:00:00", "22:00:00"),
	"Đêm (22:00-06:00)": ("22:00:00", "06:00:00"),
	"HC (07:30-16:30)": ("07:30:00", "16:30:00"),
}


class VNTShiftRegistration(Document):
	def validate(self):
		self.validate_dates()
		self.apply_kip_time()

	def validate_dates(self):
		if self.from_date and self.to_date and self.from_date > self.to_date:
			frappe.throw(_("From Date không được lớn hơn To Date"))

	def apply_kip_time(self):
		if not self.kip:
			return
		times = KIP_TIME_MAP.get(self.kip)
		if not times:
			return
		if not self.from_time:
			self.from_time = times[0]
		if not self.to_time:
			self.to_time = times[1]

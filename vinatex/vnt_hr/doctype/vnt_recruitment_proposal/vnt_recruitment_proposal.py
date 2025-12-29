# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class VNTRecruitmentProposal(Document):
	def validate(self):
		if not self.status:
			self.status = "Mới tạo"

		if self.status == "Đã phê duyệt":
			self.docstatus = 1

	def after_insert(self):
		self.create_job_requisitions()

	def create_job_requisitions(self):
		if not self.items:
			return

		status = self.get_default_job_requisition_status()
		posting_date = self.date or nowdate()
		for item in self.items:
			if self.job_requisition_exists(item.designation):
				continue

			description = item.des_detail or self.job_description or item.note or item.designation
			job_requisition = frappe.new_doc("Job Requisition")
			job_requisition.update(
				{
					"company": self.company,
					"department": self.department,
					"requested_by": self.employee,
					"posting_date": posting_date,
					"designation": item.designation,
					"no_of_positions": item.qty or 0,
					"reason_for_requesting": self.reason_for_requesting,
					"description": description,
					"custom_job_requisition_type": "Đột xuất",
					"custom_recruitment_proposal": self.name,
					"status": status,
					"expected_compensation": 0,
				}
			)
			job_requisition.insert(ignore_permissions=True)

	def job_requisition_exists(self, designation):
		return frappe.db.exists(
			"Job Requisition",
			{
				"designation": designation,
				"department": self.department,
				"requested_by": self.employee,
				"status": ("not in", ["Cancelled", "Filled"]),
			},
		)

	@staticmethod
	def get_default_job_requisition_status():
		status_field = frappe.get_meta("Job Requisition").get_field("status")
		if not status_field or not status_field.options:
			return None

		for option in status_field.options.splitlines():
			if option:
				return option

		return None

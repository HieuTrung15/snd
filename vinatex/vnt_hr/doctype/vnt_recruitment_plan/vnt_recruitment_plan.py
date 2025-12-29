# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTRecruitmentPlan(Document):
	def validate(self):
		if not self.status:
			self.status = "Tạo mới"

		if self.status == "Đã phê duyệt":
			#set docstatus to 1 (Submitted)
			self.docstatus = 1

	def after_insert(self):
		self.create_job_requisitions()

	def create_job_requisitions(self):
		if not self.items:
			return

		status = self.get_default_job_requisition_status()
		for item in self.items:
			if self.job_requisition_exists(item.designation):
				continue

			job_requisition = frappe.new_doc("Job Requisition")
			job_requisition.update(
				{
					"company": self.company,
					"department": self.department,
					"requested_by": self.employee,
					"posting_date": self.date,
					"designation": item.designation,
					"no_of_positions": item.qty,
					"expected_by": item.expected_by,
					"reason_for_requesting": item.reason_for_requesting,
					"description": item.description,
					"custom_job_requisition_type": "Theo kế hoạch",
					"custom_recruitment_plan": self.name,
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

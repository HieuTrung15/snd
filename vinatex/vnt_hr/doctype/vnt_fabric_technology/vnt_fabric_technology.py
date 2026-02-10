# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTFabricTechnology(Document):
	pass


##nếu tick vào default thì bỏ tick tất cả các bản ghi khác có cùng trường "mã vải hoàn tất"	
	def before_save(self):
		if self.default:
			existing_defaults = frappe.get_all(
				"VNT Fabric Technology",
				filters={
					"item_code": self.item_code,
					"default": 1,
					"name": ["!=", self.name],
				},
				fields=["name"],
			)
			for record in existing_defaults:
				doc = frappe.get_doc("VNT Fabric Technology", record.name)
				doc.default = 0
				doc.save()
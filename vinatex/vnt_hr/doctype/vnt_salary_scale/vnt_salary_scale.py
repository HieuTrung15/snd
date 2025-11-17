# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt


class VNTSalaryScale(Document):
	def validate(self):
		self.update_item_level_salaries()

	def update_item_level_salaries(self):
		base_salary = flt(self.regional_minimum_wage)
		if not getattr(self, "items", None):
			return

		for item in self.items:
			for index in range(1, 11):
				coefficient = flt(item.get(str(index)))
				item.set(f"ml_b{index}", base_salary * coefficient)

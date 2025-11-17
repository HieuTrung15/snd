# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt


class VNTCorporateSalary(Document):
	def validate(self):
		self.update_item_level_salaries()

	def update_item_level_salaries(self):
		base_salary = flt(self.corporate_minimum_wage)
		if not base_salary or not getattr(self, "items", None):
			return

		for item in self.items:
			for index in range(1, 13):
				coefficient_value = item.get(str(index))
				if not coefficient_value:
					continue

				coefficient = flt(coefficient_value)
				if not coefficient:
					continue

				item.set(f"ml_b{index}", base_salary * coefficient)

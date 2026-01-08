from __future__ import unicode_literals

import frappe
from frappe import _
from erpnext.stock.doctype.item.item import Item


FORCED_BATCH_GROUPS = {"Bông", "Xơ", "Thuốc nhuộm", "Hóa chất đặc thù"}


class VntItem(Item):
	def validate(self):
		super().validate()
		if (self.item_group or "").strip() in FORCED_BATCH_GROUPS and not self.has_batch_no:
			frappe.throw(
				_("Bắt buộc chọn quản lý theo lô khi hàng hóa thuộc nhóm {0}.").format(self.item_group)
			)

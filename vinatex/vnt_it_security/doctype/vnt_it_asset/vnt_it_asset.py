# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTITAsset(Document):
	def validate(self):
		self._ensure_quick_masters()

	def _ensure_quick_masters(self):
		vendor_name = (self.quick_vendor_name or "").strip()
		product_name = (self.quick_product_name or "").strip()
		asset_type_name = (self.quick_asset_type or "").strip()

		if vendor_name and not self.vendor:
			vendor_doc = _get_or_create_vendor(vendor_name, website=self.quick_vendor_website)
			self.vendor = vendor_doc.name

		if product_name and not self.product:
			vendor_for_product = self.vendor
			if not vendor_for_product:
				if vendor_name:
					vendor_doc = _get_or_create_vendor(vendor_name, website=self.quick_vendor_website)
					vendor_for_product = vendor_doc.name
					self.vendor = vendor_for_product
				else:
					frappe.throw("Vui lòng chọn hoặc nhập nhanh nhà cung cấp trước khi tạo sản phẩm.")
			product_doc = _get_or_create_product(
				product_name,
				vendor_for_product,
				family=self.quick_product_family,
				cpe_prefix=self.quick_product_cpe_prefix,
			)
			self.product = product_doc.name

		if asset_type_name and not self.asset_type:
			category = (self.quick_asset_category or "").strip() or "Hardware"
			asset_type_doc = _get_or_create_asset_type(
				asset_type_name,
				category,
				is_network_device=1 if self.quick_asset_is_network_device else 0,
			)
			self.asset_type = asset_type_doc.name


def _get_or_create_vendor(name: str, website: str | None = None):
	existing = frappe.db.get_value("VNT IT Vendor", {"vendor_name": name}, "name")
	if existing:
		return frappe.get_doc("VNT IT Vendor", existing)
	return frappe.get_doc(
		{
			"doctype": "VNT IT Vendor",
			"vendor_name": name,
			"website": website or "",
		}
	).insert(ignore_permissions=True)


def _get_or_create_product(
	name: str,
	vendor: str,
	family: str | None = None,
	cpe_prefix: str | None = None,
):
	existing = frappe.db.get_value("VNT IT Product", {"product_name": name}, "name")
	if existing:
		return frappe.get_doc("VNT IT Product", existing)
	return frappe.get_doc(
		{
			"doctype": "VNT IT Product",
			"vendor": vendor,
			"product_name": name,
			"product_family": family or "",
			"default_cpe_prefix": cpe_prefix or "",
		}
	).insert(ignore_permissions=True)


def _get_or_create_asset_type(name: str, category: str, is_network_device: int = 0):
	existing = frappe.db.get_value("VNT IT Asset Type", {"asset_type": name}, "name")
	if existing:
		return frappe.get_doc("VNT IT Asset Type", existing)
	return frappe.get_doc(
		{
			"doctype": "VNT IT Asset Type",
			"asset_type": name,
			"category": category,
			"is_network_device": is_network_device,
		}
	).insert(ignore_permissions=True)

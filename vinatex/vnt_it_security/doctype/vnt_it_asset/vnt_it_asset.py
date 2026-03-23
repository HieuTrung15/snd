# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import re

import frappe
import requests
from frappe.model.document import Document

from vinatex.vnt_itsec.sync.common import normalize_select_key


class VNTITAsset(Document):
	def validate(self):
		self._set_company_department_from_user()
		self._ensure_quick_masters()
		self._hydrate_software_components()

	def on_update(self):
		self._enqueue_itsec_automation(previous=self.get_doc_before_save())

	def _set_company_department_from_user(self):
		if self.company and self.owner_department:
			return
		user = frappe.session.user
		if not user:
			return
		emp = frappe.get_value(
			"Employee",
			{"user_id": user},
			["company", "department"],
			as_dict=True,
		)
		if not emp:
			return
		if not self.company and emp.get("company"):
			self.company = emp.company
		if not self.owner_department and emp.get("department"):
			self.owner_department = emp.department

	def _ensure_quick_masters(self):
		vendor_name = (self.quick_vendor_name or "").strip()
		product_name = (self.quick_product_name or "").strip()
		asset_type_name = (self.quick_asset_type or "").strip()

		if vendor_name and not self.vendor:
			vendor_doc = _get_or_create_vendor(vendor_name)
			self.vendor = vendor_doc.name

		if product_name and not self.product:
			vendor_for_product = self.vendor
			if not vendor_for_product:
				if vendor_name:
					vendor_doc = _get_or_create_vendor(vendor_name)
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

	def _hydrate_software_components(self):
		product_cache: dict[str, dict] = {}
		for row in self.software_components or []:
			product_name = (row.product or "").strip()
			if not product_name:
				continue

			product_doc = product_cache.get(product_name)
			if product_doc is None:
				product_doc = (
					frappe.get_value(
						"VNT IT Product",
						product_name,
						["vendor", "default_cpe_prefix"],
						as_dict=True,
					)
					or {}
				)
				product_cache[product_name] = product_doc

			if not row.vendor and product_doc.get("vendor"):
				row.vendor = product_doc["vendor"]

			row.version = (row.version or "").strip()
			row.cpe_name = (row.cpe_name or "").strip()
			if row.cpe_name and not row.cpe_name.startswith("cpe:2.3:"):
				frappe.throw(
					f"Dòng phần mềm #{row.idx}: CPE phải bắt đầu bằng 'cpe:2.3:'."
				)
			if row.cpe_name or not row.version:
				continue

			prefix = (product_doc.get("default_cpe_prefix") or "").strip()
			built_cpe = _build_cpe_name(prefix, row.version)
			if built_cpe:
				row.cpe_name = built_cpe
				continue

			suggested = _lookup_cpe_from_local(
				vendor_name=row.vendor or product_doc.get("vendor"),
				product_name=row.product,
				version=row.version,
			)
			if suggested:
				row.cpe_name = suggested

	def _enqueue_itsec_automation(self, previous=None):
		if normalize_select_key(self.lifecycle_status) != "Active":
			return
		current_snapshot = _software_snapshot(self.software_components)
		if not current_snapshot:
			return
		previous_snapshot = _software_snapshot(getattr(previous, "software_components", None))
		if previous and current_snapshot == previous_snapshot and self.company == getattr(previous, "company", None):
			return
		frappe.enqueue(
			"vinatex.vnt_itsec.automation.run_asset_inventory_automation",
			queue="long",
			job_name=f"VNT ITSEC Asset Automation {self.name}",
			asset_name=self.name,
		)


def _get_or_create_vendor(name: str):
	existing = frappe.db.get_value("VNT IT Vendor", {"vendor_name": name}, "name")
	if existing:
		return frappe.get_doc("VNT IT Vendor", existing)
	return frappe.get_doc(
		{
			"doctype": "VNT IT Vendor",
			"vendor_name": name,
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


def _build_cpe_name(prefix: str, version: str) -> str:
	prefix = (prefix or "").strip()
	version = (version or "").strip()
	if not prefix or not version:
		return ""
	if "{version}" in prefix:
		return prefix.replace("{version}", version)
	if not prefix.startswith("cpe:2.3:"):
		return ""
	if prefix.endswith(":"):
		return f"{prefix}{version}"

	parts = prefix.split(":")
	if len(parts) >= 6 and parts[5] in {"", "*", "-"}:
		parts[5] = version
		return ":".join(parts)
	return f"{prefix}:{version}"


def _software_snapshot(rows) -> tuple[tuple[str, str, str], ...]:
	values = []
	for row in rows or []:
		cpe_name = (getattr(row, "cpe_name", "") or "").strip()
		product = (getattr(row, "product", "") or "").strip()
		version = (getattr(row, "version", "") or "").strip()
		if not any((cpe_name, product, version)):
			continue
		values.append((cpe_name, product, version))
	return tuple(sorted(values))


def _normalize_cpe_fragment(value: str | None) -> str:
	raw = (value or "").strip().lower()
	raw = re.sub(r"[^a-z0-9._-]+", "_", raw)
	raw = re.sub(r"_+", "_", raw).strip("_")
	return raw


def _token_candidates(value: str | None) -> list[str]:
	base = _normalize_cpe_fragment(value)
	if not base:
		return []
	candidates = {base}
	if "-" in base:
		candidates.add(base.replace("-", "_"))
	if "_" in base:
		candidates.add(base.replace("_", "-"))
	return sorted(candidates)


def _split_cpe(cpe_name: str | None) -> list[str]:
	raw = (cpe_name or "").strip()
	if not raw.startswith("cpe:2.3:"):
		return []
	return raw.split(":")


def _cpe_version(cpe_name: str | None) -> str:
	parts = _split_cpe(cpe_name)
	if len(parts) < 6:
		return ""
	return (parts[5] or "").strip().lower()


def _version_score(cpe_version: str | None, expected_version: str | None) -> int:
	cpe_version = (cpe_version or "").strip().lower()
	expected = (expected_version or "").strip().lower()
	if not expected:
		return 0
	if cpe_version == expected:
		return 100
	if cpe_version in {"*", "-"}:
		return 30
	if cpe_version and (expected.startswith(cpe_version) or cpe_version.startswith(expected)):
		return 20
	return -60


def _candidate_score(cpe_name: str, vendor_name: str, product_name: str, version: str) -> int:
	parts = _split_cpe(cpe_name)
	if len(parts) < 6:
		return -999

	vendor = _normalize_cpe_fragment(vendor_name)
	product = _normalize_cpe_fragment(product_name)
	cpe_vendor = _normalize_cpe_fragment(parts[3])
	cpe_product = _normalize_cpe_fragment(parts[4])
	cpe_version = (parts[5] or "").strip()

	score = 0
	if cpe_vendor == vendor:
		score += 60
	elif vendor and (vendor in cpe_vendor or cpe_vendor in vendor):
		score += 25
	else:
		score -= 120

	if cpe_product == product:
		score += 70
	elif product and (product in cpe_product or cpe_product in product):
		score += 30
	else:
		score -= 120

	score += _version_score(cpe_version, version)
	return score


def _pick_best_cpe(cpe_names: list[str], vendor_name: str, product_name: str, version: str) -> str:
	best_name = ""
	best_score = -999
	for cpe_name in cpe_names:
		score = _candidate_score(cpe_name, vendor_name, product_name, version)
		if score > best_score:
			best_score = score
			best_name = cpe_name
	if best_score < 0:
		return ""
	return best_name


def _lookup_cpe_from_local(vendor_name: str | None, product_name: str | None, version: str) -> str:
	vendor_candidates = _token_candidates(vendor_name)
	product_candidates = _token_candidates(product_name)
	if not vendor_candidates or not product_candidates:
		return ""

	cpe_names: list[str] = []
	seen = set()
	for vendor_token in vendor_candidates[:3]:
		for product_token in product_candidates[:3]:
			rows = frappe.db.sql(
				"""
				select cpe_name
				from `tabVNT CVE Affected CPE`
				where cpe_name like %(like)s
				order by modified desc
				limit 150
				""",
				{"like": f"cpe:2.3:%:{vendor_token}:{product_token}:%"},
				as_dict=True,
			)
			for row in rows:
				cpe_name = (row.get("cpe_name") or "").strip()
				if not cpe_name or cpe_name in seen:
					continue
				seen.add(cpe_name)
				cpe_names.append(cpe_name)

	return _pick_best_cpe(
		cpe_names=cpe_names,
		vendor_name=vendor_name or "",
		product_name=product_name or "",
		version=version,
	)


def _lookup_cpe_from_nvd(vendor_name: str | None, product_name: str | None, version: str) -> str:
	vendor = (vendor_name or "").strip()
	product = (product_name or "").strip()
	if not vendor or not product:
		return ""

	base_url = "https://services.nvd.nist.gov/rest/json/cpes/2.0"
	headers = {"Accept": "application/json"}
	api_key = (frappe.conf.get("vnt_itsec_nvd_api_key") or "").strip()
	if api_key:
		headers["apiKey"] = api_key

	try:
		resp = requests.get(
			base_url,
			headers=headers,
			params={"keywordSearch": f"{vendor} {product}", "resultsPerPage": 150},
			timeout=20,
		)
		resp.raise_for_status()
		data = resp.json() or {}
	except Exception:
		return ""

	cpe_names: list[str] = []
	for row in (data.get("products") or []):
		cpe_obj = row.get("cpe") or {}
		cpe_name = (cpe_obj.get("cpeName") or "").strip()
		if cpe_name and cpe_name.startswith("cpe:2.3:"):
			cpe_names.append(cpe_name)

	return _pick_best_cpe(
		cpe_names=cpe_names,
		vendor_name=vendor,
		product_name=product,
		version=version,
	)


def _resolve_product_input(product: str | None, vendor: str | None) -> dict:
	info = {"product_name": (product or "").strip(), "vendor_name": (vendor or "").strip(), "default_cpe_prefix": ""}
	product_name = (product or "").strip()
	if not product_name:
		return info

	product_doc = frappe.get_value(
		"VNT IT Product",
		product_name,
		["product_name", "vendor", "default_cpe_prefix"],
		as_dict=True,
	)
	if not product_doc:
		return info

	info["product_name"] = product_doc.product_name or product_name
	info["default_cpe_prefix"] = (product_doc.default_cpe_prefix or "").strip()
	if not info["vendor_name"] and product_doc.get("vendor"):
		vendor_name = frappe.db.get_value("VNT IT Vendor", product_doc.vendor, "vendor_name")
		info["vendor_name"] = vendor_name or product_doc.vendor
	return info


@frappe.whitelist()
def suggest_cpe_name(
	product: str | None = None,
	version: str | None = None,
	vendor: str | None = None,
	use_external: int = 1,
) -> dict:
	clean_version = (version or "").strip()
	if not product or not clean_version:
		return {"ok": False, "reason": "missing_product_or_version"}

	info = _resolve_product_input(product=product, vendor=vendor)
	built = _build_cpe_name(info.get("default_cpe_prefix") or "", clean_version)
	if built:
		return {"ok": True, "cpe_name": built, "source": "product_prefix", "confidence": "High"}

	local_cpe = _lookup_cpe_from_local(
		vendor_name=info.get("vendor_name"),
		product_name=info.get("product_name"),
		version=clean_version,
	)
	if local_cpe:
		if int(use_external) and _cpe_version(local_cpe) in {"", "*", "-"}:
			nvd_cpe = _lookup_cpe_from_nvd(
				vendor_name=info.get("vendor_name"),
				product_name=info.get("product_name"),
				version=clean_version,
			)
			if nvd_cpe and _cpe_version(nvd_cpe) not in {"", "*", "-"}:
				return {"ok": True, "cpe_name": nvd_cpe, "source": "nvd_api", "confidence": "Medium"}
		return {"ok": True, "cpe_name": local_cpe, "source": "local_cache", "confidence": "Medium"}

	if int(use_external):
		nvd_cpe = _lookup_cpe_from_nvd(
			vendor_name=info.get("vendor_name"),
			product_name=info.get("product_name"),
			version=clean_version,
		)
		if nvd_cpe:
			return {"ok": True, "cpe_name": nvd_cpe, "source": "nvd_api", "confidence": "Medium"}

	return {"ok": False, "reason": "not_found"}

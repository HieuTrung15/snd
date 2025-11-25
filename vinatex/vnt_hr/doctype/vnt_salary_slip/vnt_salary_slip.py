import base64
import os
from typing import Dict, Optional

import frappe
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_bench_path


class VNTSalarySlip(Document):
	def before_save(self):
		self._update_allowance_totals()
		encrypted = self._cache_encrypted_salary_fields()
		self.tong_thu_nhap_encrypted = encrypted.get("tong_thu_nhap")
		self.thuc_linh_encrypted = encrypted.get("thuc_linh")
		self._strip_plain_salary_fields()

	def onload(self):
		self._inject_decrypted_salary_fields()

	def _update_allowance_totals(self):
		total_allowance = 0.0
		total_tax = 0.0
		total_net = 0.0

		for row in self.items or []:
			row_total = self._get_row_total(row)
			row_tax = self._get_row_tax(row)
			row_net = self._get_row_net(row_total, row_tax, row)

			if row.tong in (None, "") or abs(flt(row.tong) - row_total) > 0.0001:
				row.tong = row_total
			if row.thuc_linh in (None, "") or abs(flt(row.thuc_linh) - row_net) > 0.0001:
				row.thuc_linh = row_net

			total_allowance += row_total
			total_tax += row_tax
			total_net += row_net

		self.tong_phu_cap = total_allowance
		self.tong_thue_tncn_phu_cap = total_tax
		self.tong_thuc_linh_phu_cap = total_net

	def get_encrypted_salary_fields(self) -> Dict[str, Optional[str]]:
		"""Return ciphertexts (RSA-OAEP, base64) for tong_thu_nhap and thuc_linh."""
		return self._cache_encrypted_salary_fields()

	def _cache_encrypted_salary_fields(self) -> Dict[str, Optional[str]]:
		if hasattr(self, "_encrypted_salary_fields"):
			return self._encrypted_salary_fields

		existing_ciphertexts = {
			"tong_thu_nhap": getattr(self, "tong_thu_nhap_encrypted", None),
			"thuc_linh": getattr(self, "thuc_linh_encrypted", None),
		}
		missing_fields = [key for key, value in existing_ciphertexts.items() if not value]

		if missing_fields:
			public_key = self._get_public_key()
			if not existing_ciphertexts["tong_thu_nhap"]:
				existing_ciphertexts["tong_thu_nhap"] = self._encrypt_salary_value(
					public_key, "tong_thu_nhap", self.tong_thu_nhap
				)
			if not existing_ciphertexts["thuc_linh"]:
				existing_ciphertexts["thuc_linh"] = self._encrypt_salary_value(
					public_key, "thuc_linh", self.thuc_linh
				)

		self._encrypted_salary_fields = existing_ciphertexts
		return existing_ciphertexts

	def _encrypt_salary_value(
		self, public_key, field_name: str, value: Optional[float]
	) -> Optional[str]:
		if value in (None, ""):
			return None

		plaintext = f"{flt(value):.3f}".encode()
		ciphertext = public_key.encrypt(
			plaintext,
			padding.OAEP(
				mgf=padding.MGF1(algorithm=hashes.SHA256()),
				algorithm=hashes.SHA256(),
				label=None,
			),
		)
		# frappe.throw(base64.b64encode(ciphertext).decode())
		return base64.b64encode(ciphertext).decode()

	@staticmethod
	def _load_site_env() -> Dict[str, str]:
		bench_path = get_bench_path()
		env_path = os.path.join(bench_path, "sites", ".env")

		if not os.path.exists(env_path):
			frappe.throw(_("Missing {0} file with VNT_PUBLIC_KEY and VNT_PRIVATE_KEY.").format(env_path))

		env_values: Dict[str, str] = {}
		with open(env_path, encoding="utf-8") as env_file:
			for line in env_file:
				strip_line = line.strip()
				if not strip_line or strip_line.startswith("#") or "=" not in strip_line:
					continue
				key, value = strip_line.split("=", 1)
				env_values[key.strip()] = value.strip()

		if "VNT_PRIVATE_KEY" not in env_values:
			frappe.throw(_("VNT_PRIVATE_KEY is missing in {0}").format(env_path))

		return env_values


	def _get_public_key(self):
		env_values = self._load_site_env()
		raw_public = env_values.get("VNT_PUBLIC_KEY")
		if not raw_public:
			frappe.throw(_("VNT_PUBLIC_KEY is missing in sites/.env"))

		try:
			public_pem = base64.b64decode(raw_public)
			return serialization.load_pem_public_key(public_pem)
		except Exception as exc:
			frappe.throw(_("Invalid VNT_PUBLIC_KEY in sites/.env: {0}").format(frappe.as_unicode(exc)))

	@staticmethod
	def _get_private_key():
		env_values = VNTSalarySlip._load_site_env()
		raw_private = env_values.get("VNT_PRIVATE_KEY")
		if not raw_private:
			frappe.throw(_("VNT_PRIVATE_KEY is missing in sites/.env"))

		try:
			private_pem = base64.b64decode(raw_private)
			return serialization.load_pem_private_key(private_pem, password=None)
		except Exception as exc:
			frappe.throw(_("Invalid VNT_PRIVATE_KEY in sites/.env: {0}").format(frappe.as_unicode(exc)))

	@staticmethod
	def _decrypt_salary_value(ciphertext_b64: Optional[str]) -> Optional[float]:
		if not ciphertext_b64:
			return None
		private_key = VNTSalarySlip._get_private_key()
		try:
			plaintext = private_key.decrypt(
				base64.b64decode(ciphertext_b64),
				padding.OAEP(
					mgf=padding.MGF1(algorithm=hashes.SHA256()),
					algorithm=hashes.SHA256(),
					label=None,
				),
			)
			return flt(plaintext.decode())
		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), _("Failed to decrypt salary fields"))
			frappe.throw(_("Không giải mã được dữ liệu lương. Vui lòng liên hệ quản trị viên. {0}").format(frappe.as_unicode(exc)))

	def _inject_decrypted_salary_fields(self):
		"""Populate plaintext fields for UI usage only; values are not persisted."""
		tong_cipher = getattr(self, "tong_thu_nhap_encrypted", None)
		if tong_cipher:
			self.tong_thu_nhap = VNTSalarySlip._decrypt_salary_value(tong_cipher)

		thuc_cipher = getattr(self, "thuc_linh_encrypted", None)
		if thuc_cipher:
			self.thuc_linh = VNTSalarySlip._decrypt_salary_value(thuc_cipher)

	def _strip_plain_salary_fields(self):
		"""Ensure plaintext amounts are not stored in DB."""
		self.tong_thu_nhap = None
		self.thuc_linh = None

	@staticmethod
	def decrypt_salary_values(
		tong_thu_nhap_encrypted: Optional[str] = None, thuc_linh_encrypted: Optional[str] = None
	) -> Dict[str, Optional[float]]:
		"""Shared helper to decrypt salary ciphertexts (RSA-OAEP, base64)."""
		return {
			"tong_thu_nhap": VNTSalarySlip._decrypt_salary_value(tong_thu_nhap_encrypted)
			if tong_thu_nhap_encrypted
			else None,
			"thuc_linh": VNTSalarySlip._decrypt_salary_value(thuc_linh_encrypted)
			if thuc_linh_encrypted
			else None,
		}

	@staticmethod
	def _get_row_total(row) -> float:
		if row.tong not in (None, ""):
			return flt(row.tong)
		return flt(row.amount) * flt(row.so_thang)

	@staticmethod
	def _get_row_tax(row) -> float:
		return flt(row.thue_tncn)

	@staticmethod
	def _get_row_net(row_total: float, row_tax: float, row) -> float:
		if row.thuc_linh not in (None, ""):
			return flt(row.thuc_linh)
		return row_total - row_tax


@frappe.whitelist()
def get_encrypted_salary_fields(name: str) -> Dict[str, Optional[str]]:
	"""API helper to fetch encrypted salary fields for a given salary slip."""
	slip: VNTSalarySlip = frappe.get_doc("VNT Salary Slip", name)
	return slip.get_encrypted_salary_fields()

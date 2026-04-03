import base64
import json
import os
from functools import lru_cache
from typing import Dict, Optional

import frappe
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, flt, get_bench_path
from vinatex.vnt_hr.permissions import is_hr_salary_user


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
		if getattr(VNTSalarySlip, "_public_key_cache", None):
			return VNTSalarySlip._public_key_cache

		env_values = self._load_site_env()
		raw_public = env_values.get("VNT_PUBLIC_KEY")
		if not raw_public:
			frappe.throw(_("VNT_PUBLIC_KEY is missing in sites/.env"))

		try:
			public_pem = base64.b64decode(raw_public)
			VNTSalarySlip._public_key_cache = serialization.load_pem_public_key(public_pem)
			return VNTSalarySlip._public_key_cache
		except Exception as exc:
			frappe.throw(_("Invalid VNT_PUBLIC_KEY in sites/.env: {0}").format(frappe.as_unicode(exc)))

	@staticmethod
	def _get_private_key():
		if getattr(VNTSalarySlip, "_private_key_cache", None):
			return VNTSalarySlip._private_key_cache

		env_values = VNTSalarySlip._load_site_env()
		raw_private = env_values.get("VNT_PRIVATE_KEY")
		if not raw_private:
			frappe.throw(_("VNT_PRIVATE_KEY is missing in sites/.env"))

		try:
			private_pem = base64.b64decode(raw_private)
			VNTSalarySlip._private_key_cache = serialization.load_pem_private_key(private_pem, password=None)
			return VNTSalarySlip._private_key_cache
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

	@staticmethod
	@lru_cache(maxsize=512)
	def _cached_decrypt(ciphertext_b64: Optional[str]) -> Optional[float]:
		return VNTSalarySlip._decrypt_salary_value(ciphertext_b64)

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
			"tong_thu_nhap": VNTSalarySlip._cached_decrypt(tong_thu_nhap_encrypted)
			if tong_thu_nhap_encrypted
			else None,
			"thuc_linh": VNTSalarySlip._cached_decrypt(thuc_linh_encrypted)
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


def _get_monthly_payroll_name(slip: VNTSalarySlip) -> Optional[str]:
	if not slip or not slip.employee or not slip.month or not slip.year:
		return None

	month_str = str(slip.month).zfill(2)
	year_val = slip.year
	sql = """
		SELECT parent.name
		FROM `tabVNT Monthly Payroll Item` item
		INNER JOIN `tabVNT Monthly Payroll` parent ON parent.name = item.parent
		WHERE item.employee = %(employee)s
		  AND parent.month = %(month)s
		  AND parent.year = %(year)s
		ORDER BY parent.creation DESC
		LIMIT 1
	"""
	rows = frappe.db.sql(sql, {"employee": slip.employee, "month": month_str, "year": year_val}, as_dict=True)
	return rows[0]["name"] if rows else None


def _get_employee_display_info(slip: VNTSalarySlip) -> Dict[str, str]:
	employee_name = (slip.get("employee_name") or "").strip()
	designation = (slip.get("designation") or "").strip()
	if slip.employee and (not employee_name or not designation):
		employee_info = frappe.db.get_value("Employee", slip.employee, ["employee_name", "designation"], as_dict=True) or {}
		if not employee_name:
			employee_name = (employee_info.get("employee_name") or "").strip()
		if not designation:
			designation = (employee_info.get("designation") or "").strip()
	return {"employee_name": employee_name, "designation": designation}


def render_salary_slip_html(slip: VNTSalarySlip, payroll_name: Optional[str] = None) -> str:
	def fmt_number(value, decimals=0, blank_for_zero=False):
		if value is None:
			return ""
		number = flt(value, decimals)
		if blank_for_zero and abs(number) < 0.0001:
			return ""
		if decimals:
			formatted = f"{number:,.{decimals}f}"
		else:
			formatted = f"{int(round(number)):,}"
		return formatted

	def fmt_currency(value, blank_for_zero=True):
		if value is None:
			return ""
		amount = flt(value, 2)
		if blank_for_zero and abs(amount) < 0.0001:
			return ""
		formatted = f"{amount:,.0f}"
		if formatted == "0" and blank_for_zero:
			return ""
		return formatted

	def section_row(idx, title, value="", row_class="section-row"):
		idx_html = escape_html(idx) if idx else ""
		title_html = escape_html(title)
		value_html = escape_html(value) if value else ""
		return (
			f'<tr class="{row_class}">'
			f'<td class="index">{idx_html}</td>'
			f'<td class="label">{title_html}</td>'
			f'<td class="colon">:</td>'
			f'<td class="value">{value_html}</td>'
			f"</tr>"
		)

	def value_row(idx, label, value, indent=False):
		label_html = escape_html(label)
		value_html = escape_html(value) if value else ""
		index_html = escape_html(idx) if idx else ""
		indent_class = " indent" if indent else ""
		return (
			f"<tr>"
			f'<td class="index">{index_html}</td>'
			f'<td class="label{indent_class}">{label_html}</td>'
			f'<td class="colon">:</td>'
			f'<td class="value">{value_html}</td>'
			f"</tr>"
		)

	thue_nam_truoc = slip.thue_tncn_nam_truoc
	if thue_nam_truoc in (None, ""):
		thue_nam_truoc = flt(slip.get("truy_thu")) - flt(slip.get("duoc_hoan_lai"))

	display_info = _get_employee_display_info(slip)
	employee_name = display_info.get("employee_name")
	designation = display_info.get("designation")

	month_str = str(slip.month or "").zfill(2)
	year_str = str(slip.year or "")

	rows = [
		section_row("A", f"LUONG THANG {month_str}/{year_str}", row_class="section-row period-row"),
		section_row("I", "THÔNG TIN CHUNG"),
		value_row("1", "Số ngày công", fmt_number(slip.so_ngay_cong, 1)),
		value_row("2", "Số ngày nghỉ tính phép", fmt_number(slip.so_ngay_nghi_tinh_phep, 1)),
		value_row(
			"3",
			"Số ngày nghỉ việc riêng có hưởng lương",
			fmt_number(slip.so_ngay_nghi_viec_rieng_co_huong_luong, 1),
		),
		value_row(
			"4",
			"Số ngày nghỉ không lương/ Nghỉ ốm/ TS nam",
			fmt_number(slip.so_ngay_nghi_khong_luong, 1),
		),
		value_row("5", "Hệ số lương cơ bản", fmt_number(slip.he_so_luong_co_ban, 1)),
		value_row("6", "Hệ số phụ cấp", ""),
		value_row("", "a. Trách nhiệm Đảng", fmt_number(slip.hs_pc_dang, 1), indent=True),
		value_row(
			"",
			"b. Kiêm nhiệm Đoàn thể",
			fmt_number(slip.hs_pc_kiem_nhiem, 1),
			indent=True,
		),
		value_row("7", "Tiền lương tính BHXH", ""),
		value_row("", "a. Lương cơ bản", fmt_currency(slip.luong_co_ban), indent=True),
		value_row("", "a. PC trách nhiệm Đảng", fmt_currency(slip.pc_dang), indent=True),
		value_row("", "b. PC kiêm nhiệm Đoàn thể", fmt_currency(slip.pc_kiem_nhiem), indent=True),
		value_row("8", "Số người phụ thuộc", fmt_number(slip.so_nguoi_phu_thuoc, 1)),
		section_row("II", "TỔNG THU NHẬP", fmt_currency(slip.tong_thu_nhap, blank_for_zero=False), row_class="section-row total-row"),
		value_row("1", "Hệ số lương CBCV", fmt_number(slip.he_so_luong_cbcv, 1)),
		value_row("2", "Lương CBCV", fmt_currency(slip.luong_cbcv)),
		value_row("3", "Phụ cấp", ""),
		value_row("", "a. Trách nhiệm Đảng", fmt_currency(slip.pc_dang2), indent=True),
		value_row("", "b. Kiêm nhiệm Đoàn thể", fmt_currency(slip.pc_kiem_nhiem2), indent=True),
		value_row("", "c. PC đặc thù", fmt_currency(slip.get("pc_dac_thu")), indent=True),
		value_row("", "d. PC Chuyển đổi số", fmt_currency(slip.get("pc_chuyen_doi_so")), indent=True),
		value_row("", "e. PC BCH Quân sự", fmt_currency(slip.get("pc_bch_quan_su")), indent=True),
		value_row("4", "Thù lao (HĐQT, Ban KS)", fmt_currency(slip.get("thu_lao_hdqt"))),
		value_row("5", "Tiền lương CQĐH, KTT", fmt_currency(slip.get("tien_luong_hqcv_cu"))),
		value_row("6", "Lương ngày phép", fmt_currency(slip.luong_ngay_phep)),
		value_row(
			"7",
			"Lương ngày nghỉ VR có hưởng lương",
			fmt_currency(slip.luong_ngay_nghi_co_huong_luong),
		),
		value_row("8", "Truy lĩnh", fmt_currency(slip.truy_linh, blank_for_zero=False)),
		value_row("9", "Tiền ăn ca", fmt_currency(slip.tien_an_ca)),
		value_row("10", "Tiền khoán CP điện thoại", fmt_currency(slip.get("tien_khoan_pc_dien_thoai"))),
		value_row("11", "Khoản công tác phí", fmt_currency(slip.cong_tac_phi)),
		value_row("12", "Thuế TNCN được hoàn", fmt_currency(slip.get("duoc_hoan_lai"), blank_for_zero=False)),
		section_row("III", "CÁC KHOẢN TRỪ VÀO LƯƠNG"),
		value_row("1", "BHXH, BHYT, BHTN (10,5%)", fmt_currency(slip.xh_yt_tn, blank_for_zero=False)),
		value_row("2", "Công đoàn phí (0,5%)", fmt_currency(slip.cong_doan, blank_for_zero=False)),
		value_row("3", "Đảng phí", fmt_currency(slip.get("dang_phi"), blank_for_zero=False)),
		value_row("4", "Thuế TNCN tạm thu", fmt_currency(slip.thue_tncn, blank_for_zero=False)),
	]

	if abs(flt(thue_nam_truoc)) > 0.0001:
		rows.append(value_row("5", "Thuế TNCN năm trước", fmt_currency(thue_nam_truoc, blank_for_zero=False)))

	rows.append(value_row("6", "Khác (...)", fmt_currency(slip.get("khac"), blank_for_zero=False)))
	rows.append(section_row("IV", "THỰC LĨNH (II-III)", fmt_currency(slip.thuc_linh, blank_for_zero=False), row_class="section-row total-row"))

	style = (
		"<style>"
		".salary-slip-wrapper{font-size:16px;line-height:1.2;font-family:'Times New Roman',Times,serif;color:#111;}"  # noqa: E501
		".salary-slip-company{font-size:17px;font-weight:700;}"
		".salary-slip-company + .salary-slip-company{margin-top:2px;}"
		".salary-slip-title{margin:18px 0 16px;text-align:center;font-size:34px;font-weight:700;}"
		".salary-slip-meta{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;}"
		".salary-slip-meta-left{font-size:16px;}"
		".salary-slip-meta-row{margin-bottom:2px;display:flex;align-items:flex-start;}"
		".salary-slip-meta-label{display:inline-block;width:110px;font-weight:700;}"
		".salary-slip-meta-colon{display:inline-block;width:14px;text-align:center;font-weight:700;}"
		".salary-slip-meta-name{color:#c50000;font-style:italic;font-weight:700;}"
		".salary-slip-meta-designation{font-style:italic;font-weight:700;}"
		".salary-slip-meta-unit{font-size:16px;font-weight:700;margin-top:24px;}"
		".salary-slip-table{width:100%;border-collapse:collapse;}"
		".salary-slip-table td{border:1px solid #2e2e2e;padding:3px 6px;vertical-align:middle;font-size:16px;}"
		".salary-slip-table .section-row td{background:#c8d1e2;font-weight:700;text-transform:uppercase;}"
		".salary-slip-table .section-row.total-row td{font-weight:800;}"
		".salary-slip-table .period-row td{color:#c50000;font-weight:800;}"
		".salary-slip-table .index{width:42px;text-align:center;font-weight:700;}"
		".salary-slip-table .label{width:58%;}"
		".salary-slip-table .label.indent{padding-left:24px;}"
		".salary-slip-table .colon{width:18px;text-align:center;font-weight:700;}"
		".salary-slip-table .value{width:28%;text-align:right;font-weight:700;}"
		"</style>"
	)

	header = (
		f'<div class="salary-slip-company">TẬP ĐOÀN DỆT MAY VIỆT NAM</div>'
		f'<div class="salary-slip-company">BAN QUẢN LÝ NNL</div>'
		f'<div class="salary-slip-title">BẢNG LƯƠNG CÁ NHÂN</div>'
		f'<div class="salary-slip-meta">'
		f'<div class="salary-slip-meta-left">'
		f'<div class="salary-slip-meta-row"><span class="salary-slip-meta-label">Họ và tên</span><span class="salary-slip-meta-colon">:</span><span class="salary-slip-meta-name">{escape_html(employee_name or slip.employee or "")}</span></div>'  # noqa: E501
		f'<div class="salary-slip-meta-row"><span class="salary-slip-meta-label">Chức vụ</span><span class="salary-slip-meta-colon">:</span><span class="salary-slip-meta-designation">{escape_html(designation or "")}</span></div>'  # noqa: E501
		f"</div>"
		f'<div class="salary-slip-meta-unit">Đơn vị: đồng</div>'
		f"</div>"
	)

	table_html = "".join(rows)
	return f'<div class="salary-slip-wrapper">{style}{header}<table class="salary-slip-table">{table_html}</table></div>'


def _render_salary_slip_html(slip: VNTSalarySlip) -> str:
	return render_salary_slip_html(slip)


@frappe.whitelist()
def get_rendered_html(name: str) -> str:
	if not name:
		return ""
	slip: VNTSalarySlip = frappe.get_doc("VNT Salary Slip", name)
	if slip.rendered_html:
		return slip.rendered_html
	slip._inject_decrypted_salary_fields()
	html = _render_salary_slip_html(slip)
	if html:
		frappe.db.set_value("VNT Salary Slip", slip.name, {"rendered_html": html})
		slip.rendered_html = html
	return html


@frappe.whitelist()
def backfill_rendered_html(name: Optional[str] = None, month: Optional[str] = None, year: Optional[int] = None,
	employee: Optional[str] = None, limit: int = 200) -> Dict[str, int]:
	if not is_hr_salary_user(frappe.session.user) and "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Bạn không có quyền cập nhật HTML hàng loạt."))
	limit = int(limit or 0)
	if limit <= 0:
		limit = 200

	params = {"limit": limit}
	conditions = ["docstatus != 2"]

	if name:
		conditions.append("name = %(name)s")
		params["name"] = name
	if employee:
		conditions.append("employee = %(employee)s")
		params["employee"] = employee
	if month:
		conditions.append("month = %(month)s")
		params["month"] = str(month).zfill(2)
	if year:
		conditions.append("year = %(year)s")
		params["year"] = int(year)

	if not name:
		conditions.append("(rendered_html IS NULL OR rendered_html = '')")

	where_clause = " AND ".join(conditions)
	sql = f"""
		SELECT name
		FROM `tabVNT Salary Slip`
		WHERE {where_clause}
		ORDER BY modified DESC
		LIMIT %(limit)s
	"""
	rows = frappe.db.sql(sql, params, as_dict=True)
	names = [row["name"] for row in rows if row.get("name")]

	updated = 0
	for slip_name in names:
		slip: VNTSalarySlip = frappe.get_doc("VNT Salary Slip", slip_name)
		if slip.rendered_html:
			continue
		slip._inject_decrypted_salary_fields()
		html = _render_salary_slip_html(slip)
		if not html:
			continue
		frappe.db.set_value("VNT Salary Slip", slip.name, {"rendered_html": html}, update_modified=False)
		updated += 1

	return {"processed": len(names), "updated": updated}


def _backfill_rendered_html_job(batch_size: int = 200) -> Dict[str, int]:
	batch_size = int(batch_size or 0)
	if batch_size <= 0:
		batch_size = 200

	total_processed = 0
	total_updated = 0

	while True:
		rows = frappe.db.sql(
			"""
			SELECT name
			FROM `tabVNT Salary Slip`
			WHERE docstatus != 2
			  AND (rendered_html IS NULL OR rendered_html = '')
			ORDER BY modified DESC
			LIMIT %(limit)s
			""",
			{"limit": batch_size},
			as_dict=True,
		)
		names = [row["name"] for row in rows if row.get("name")]
		if not names:
			break

		total_processed += len(names)
		for slip_name in names:
			slip: VNTSalarySlip = frappe.get_doc("VNT Salary Slip", slip_name)
			if slip.rendered_html:
				continue
			slip._inject_decrypted_salary_fields()
			html = _render_salary_slip_html(slip)
			if not html:
				continue
			frappe.db.set_value("VNT Salary Slip", slip.name, {"rendered_html": html}, update_modified=False)
			total_updated += 1

		frappe.db.commit()

	return {"processed": total_processed, "updated": total_updated}


@frappe.whitelist()
def enqueue_backfill_rendered_html_all(batch_size: int = 200) -> Dict[str, str]:
	if not is_hr_salary_user(frappe.session.user) and "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Bạn không có quyền cập nhật HTML hàng loạt."))

	frappe.enqueue(
		"vinatex.vnt_hr.doctype.vnt_salary_slip.vnt_salary_slip._backfill_rendered_html_job",
		queue="long",
		timeout=600,
		is_async=True,
		batch_size=batch_size,
	)
	return {"status": "queued"}


@frappe.whitelist()
def get_encrypted_salary_fields(name: str) -> Dict[str, Optional[str]]:
	"""API helper to fetch encrypted salary fields for a given salary slip."""
	slip: VNTSalarySlip = frappe.get_doc("VNT Salary Slip", name)
	return slip.get_encrypted_salary_fields()


def _needs_decryption(value, ciphertext) -> bool:
	"""Return True if ciphertext exists and the plaintext field is empty or zero."""
	if not ciphertext:
		return False
	if value in (None, ""):
		return True
	try:
		return flt(value) == 0
	except Exception:
		return False


@frappe.whitelist()
def get_decrypted_salary_for_list(names) -> Dict[str, Dict[str, float]]:
	"""
	Trả về map {name: {tong_thu_nhap, thuc_linh}} đã giải mã cho List View.
	`names` có thể là list hoặc chuỗi JSON.
	"""
	if not names:
		return {}

	if isinstance(names, str):
		try:
			names = json.loads(names)
		except Exception:
			names = [names]

	if not isinstance(names, (list, tuple, set)):
		names = [names]

	names = [n for n in names if n]
	if not names:
		return {}

	rows = frappe.db.get_all(
		"VNT Salary Slip",
		filters={"name": ["in", names]},
		fields=["name", "tong_thu_nhap", "thuc_linh", "tong_thu_nhap_encrypted", "thuc_linh_encrypted"],
	)

	result: Dict[str, Dict[str, float]] = {}
	for row in rows:
		gross = row.get("tong_thu_nhap")
		net = row.get("thuc_linh")
		if _needs_decryption(gross, row.get("tong_thu_nhap_encrypted")) or _needs_decryption(net, row.get("thuc_linh_encrypted")):
			decrypted = VNTSalarySlip.decrypt_salary_values(
				tong_thu_nhap_encrypted=row.get("tong_thu_nhap_encrypted"),
				thuc_linh_encrypted=row.get("thuc_linh_encrypted"),
			)
			if _needs_decryption(gross, row.get("tong_thu_nhap_encrypted")):
				gross = decrypted.get("tong_thu_nhap")
			if _needs_decryption(net, row.get("thuc_linh_encrypted")):
				net = decrypted.get("thuc_linh")

		result[row["name"]] = {
			"tong_thu_nhap": flt(gross),
			"thuc_linh": flt(net),
		}

	return result

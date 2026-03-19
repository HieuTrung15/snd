from __future__ import annotations

import base64
import binascii
import time
from collections.abc import Mapping

import frappe
from frappe import _
from frappe.exceptions import AuthenticationError, PermissionError
from frappe.utils import getdate
from frappe.utils.file_manager import save_file
from frappe.utils.password import get_decrypted_password


INCOMING_SERIES = "CVĐEN.-.YY.-.####"
OUTGOING_SERIES = "CVĐI.-.YY.-.####"
DEFAULT_AUTH_SOURCE = "User"
REQUEST_META_KEYS = {"cmd", "data", "csrf_token"}
PDF_FILE_FIELDS = ("attachment", "file", "pdf_file", "attach")
PDF_BASE64_FIELDS = ("attachment_base64", "file_base64", "pdf_base64")
PDF_FILENAME_FIELDS = ("attachment_filename", "file_name", "filename", "pdf_filename")
LOG_DOCTYPE = "VNT API Integration Log"


@frappe.whitelist()
def create_incoming_document(**kwargs):
	return _execute_logged_api(
		operation="Công văn đến",
		endpoint="vinatex.api.document_management.create_incoming_document",
		doc_factory=_create_incoming_document,
		kwargs=kwargs,
	)


@frappe.whitelist()
def create_outgoing_document(**kwargs):
	return _execute_logged_api(
		operation="Công văn đi",
		endpoint="vinatex.api.document_management.create_outgoing_document",
		doc_factory=_create_outgoing_document,
		kwargs=kwargs,
	)


def _execute_logged_api(
	operation: str,
	endpoint: str,
	doc_factory,
	kwargs: Mapping[str, object] | None = None,
):
	started = time.perf_counter()
	payload = _get_request_payload(kwargs)
	attachment = None
	auth_context = _extract_auth_context()
	savepoint = f"api_log_{frappe.generate_hash(length=10)}"
	frappe.db.savepoint(savepoint)

	try:
		_require_post()
		attachment = _extract_pdf_attachment(payload)
		auth_context = _require_api_key_auth(auth_context=auth_context)
		doc = doc_factory(payload, attachment=attachment)
		response = _build_response(doc)
		_insert_api_log(
			status="Success",
			operation=operation,
			endpoint=endpoint,
			request_payload=payload,
			response_payload=response,
			auth_context=auth_context,
			attachment=attachment,
			doc=doc,
			duration_ms=_duration_ms(started),
		)
		return response
	except Exception as exc:
		frappe.db.rollback(save_point=savepoint)
		_insert_api_log(
			status="Failure",
			operation=operation,
			endpoint=endpoint,
			request_payload=payload,
			response_payload={"error": _safe_error_message(exc)},
			auth_context=auth_context,
			attachment=attachment,
			doc=None,
			duration_ms=_duration_ms(started),
			error_text=frappe.get_traceback(),
			exc=exc,
			commit=True,
		)
		raise


def _create_incoming_document(payload: Mapping[str, object], attachment: tuple[str, bytes] | None = None):
	document_date = _require_date(payload, "Ngày văn bản", "document_date", "ngay_van_ban")
	received_date = _require_date(payload, "Ngày đến", "received_date", "ngay_den")
	deadline = _require_date(payload, "Thời hạn", "deadline", "thoi_han")
	reference_number = _require_text(payload, "Số hiệu văn bản", "reference_number", "so_hieu_van_ban")
	sender = _require_text(payload, "Nơi gửi", "sender", "noi_gui")
	summary = _require_text(payload, "Trích yếu", "summary", "trich_yeu")
	creator_employee = _get_current_employee()

	doc = frappe.new_doc("VNT Document Management")
	doc.update(
		{
			"type": "Công văn đến",
			"vnt_type": "Công văn đến",
			"naming_series": INCOMING_SERIES,
			"document_date": document_date,
			"received_date": received_date,
			"deadline": deadline,
			"reference_number": reference_number,
			"sender": sender,
			"summary": summary,
			"internal": 0,
		}
	)
	if creator_employee:
		doc.employee = creator_employee

	doc.insert(ignore_permissions=True, ignore_mandatory=True)

	if attachment:
		doc.db_set("attach", _save_attachment(doc, attachment), update_modified=False)

	return doc


def _create_outgoing_document(payload: Mapping[str, object], attachment: tuple[str, bytes] | None = None):
	document_date = _require_date(payload, "Ngày văn bản", "document_date", "ngay_van_ban")
	reference_number = _require_text(payload, "Số hiệu văn bản", "reference_number", "so_hieu_van_ban")
	department = _resolve_department(_require_text(payload, "Ban gửi đi", "department", "ban_gui_di"))
	signer_email = _require_text(payload, "Email người ký", "signer_email", "nguoi_ky_email", "nguoi_ky")
	signer_employee = _resolve_employee_by_email(signer_email)
	summary = _require_text(payload, "Trích yếu", "summary", "trich_yeu")
	incoming_document = _resolve_incoming_document(
		_require_text(payload, "Công văn đến tương ứng", "incoming_document", "cong_van_den", "vnt_doc_mng")
	)
	recipient = _require_text(payload, "Nơi nhận", "noi_nhan", "recipient")
	deadline = _optional_date(payload, "deadline", "thoi_han")
	creator_employee = _get_current_employee()

	doc = frappe.new_doc("VNT Document Management")
	doc.update(
		{
			"type": "Công văn đi",
			"vnt_type": "Công văn đi",
			"naming_series": OUTGOING_SERIES,
			"document_date": document_date,
			"received_date": document_date,
			"reference_number": reference_number,
			"department": department,
			"nguoi_ky": signer_employee,
			"summary": summary,
			"vnt_doc_mng": incoming_document,
			"noi_nhan": recipient,
		}
	)
	if creator_employee:
		doc.employee = creator_employee
	if deadline:
		doc.deadline = deadline

	doc.insert(ignore_permissions=True, ignore_mandatory=True)

	if attachment:
		doc.db_set("attach", _save_attachment(doc, attachment), update_modified=False)

	return doc


def _require_post():
	request = getattr(frappe.local, "request", None)
	method = getattr(request, "method", None)
	if method and str(method).upper() != "POST":
		frappe.throw("API này chỉ hỗ trợ phương thức POST.")


def _require_api_key_auth(auth_context: dict[str, object] | None = None):
	auth_context = auth_context or _extract_auth_context()
	header = str(auth_context.get("authorization_header") or "").strip()
	if not header:
		raise AuthenticationError(
			"Thiếu header Authorization. Dùng định dạng 'Authorization: token api_key:api_secret'."
		)

	auth_type = str(auth_context.get("auth_type") or "").strip().lower()
	api_key = str(auth_context.get("api_key") or "")
	api_secret = str(auth_context.get("api_secret") or "")
	if not auth_type or not header:
		raise AuthenticationError("Header Authorization không hợp lệ.")

	if auth_type not in {"token", "basic"}:
		raise AuthenticationError("Chỉ hỗ trợ Authorization kiểu token hoặc basic.")
	if not api_key or not api_secret:
		raise AuthenticationError("Header Authorization phải chứa api_key:api_secret hợp lệ.")

	auth_source = str(auth_context.get("auth_source") or DEFAULT_AUTH_SOURCE)
	docname = frappe.db.get_value(
		doctype=auth_source,
		filters={"api_key": api_key, "enabled": True},
		fieldname="name",
	)
	if not docname:
		raise AuthenticationError("API key không hợp lệ hoặc tài khoản đã bị khóa.")

	doc_secret = get_decrypted_password(auth_source, docname, fieldname="api_secret", raise_exception=False)
	if not doc_secret or api_secret != doc_secret:
		raise AuthenticationError("API secret không hợp lệ.")

	user = docname if auth_source == "User" else frappe.db.get_value(auth_source, docname, "user")
	if not user:
		raise AuthenticationError("Không xác định được user của API key này.")

	frappe.set_user(user)
	auth_context["auth_source"] = auth_source
	auth_context["api_key_prefix"] = _api_key_prefix(api_key)
	auth_context["api_user"] = user
	return auth_context


def _get_request_payload(kwargs: Mapping[str, object] | None = None) -> dict[str, object]:
	payload: dict[str, object] = {}
	request = getattr(frappe.local, "request", None)

	if request:
		json_payload = request.get_json(silent=True)
		if isinstance(json_payload, Mapping):
			payload.update(_clean_mapping(json_payload))
		form_payload = getattr(request, "form", None)
		if form_payload:
			payload.update(_clean_mapping(form_payload))

	if kwargs:
		payload.update(_clean_mapping(kwargs))

	form_dict = getattr(frappe.local, "form_dict", None)
	if isinstance(form_dict, Mapping):
		payload.update(_clean_mapping(form_dict))

	return payload


def _clean_mapping(data: Mapping[str, object]) -> dict[str, object]:
	cleaned: dict[str, object] = {}
	for key, value in data.items():
		if key in REQUEST_META_KEYS:
			continue
		cleaned[key] = value
	return cleaned


def _extract_pdf_attachment(payload: Mapping[str, object]) -> tuple[str, bytes] | None:
	request = getattr(frappe.local, "request", None)
	files = getattr(request, "files", None)
	if files:
		for fieldname in PDF_FILE_FIELDS:
			uploaded = files.get(fieldname)
			if not uploaded:
				continue
			filename = (uploaded.filename or "").strip() or "attachment.pdf"
			content = uploaded.read()
			_validate_pdf_bytes(filename, content)
			return filename, content

	base64_content = _first_present(payload, *PDF_BASE64_FIELDS)
	if not base64_content:
		return None

	filename = str(_first_present(payload, *PDF_FILENAME_FIELDS) or "attachment.pdf").strip()
	if "," in str(base64_content):
		base64_content = str(base64_content).split(",", 1)[1]

	try:
		content = base64.b64decode(base64_content, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw("File PDF base64 không hợp lệ.")

	_validate_pdf_bytes(filename, content)
	return filename, content


def _validate_pdf_bytes(filename: str, content: bytes):
	if not content:
		frappe.throw("File đính kèm PDF đang rỗng.")
	if not filename.lower().endswith(".pdf") and not content.startswith(b"%PDF"):
		frappe.throw("Chỉ chấp nhận file đính kèm định dạng PDF.")


def _save_attachment(doc, attachment: tuple[str, bytes]) -> str:
	filename, content = attachment
	file_doc = save_file(filename, content, doc.doctype, doc.name, is_private=0)
	return file_doc.file_url


def _build_response(doc) -> dict[str, object]:
	return {
		"success": True,
		# "doctype": doc.doctype,
		"name": doc.name,
		"reference_number": doc.reference_number,
		# "attach": doc.attach,
	}


def _get_current_employee() -> str | None:
	user = frappe.session.user
	if not user or user == "Guest":
		return None

	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if employee:
		return employee

	match = frappe.db.sql(
		"""
		select name
		from `tabEmployee`
		where lower(ifnull(user_id, '')) = lower(%s)
		limit 1
		""",
		(user,),
	)
	return match[0][0] if match else None


def _resolve_employee_by_email(email: str) -> str:
	email = email.strip()
	employee = frappe.db.get_value("Employee", {"user_id": email}, "name")
	if employee:
		return employee

	rows = frappe.db.sql(
		"""
		select name
		from `tabEmployee`
		where lower(ifnull(user_id, '')) = lower(%s)
		limit 2
		""",
		(email,),
		as_dict=True,
	)
	if not rows:
		frappe.throw(f"Không tìm thấy Employee theo email người ký: {email}.")
	if len(rows) > 1:
		frappe.throw(f"Email người ký {email} map ra nhiều Employee, cần làm sạch dữ liệu.")
	return rows[0]["name"]


def _resolve_department(department_value: str) -> str:
	department_value = department_value.strip()
	if frappe.db.exists("Department", department_value):
		return department_value

	exact_name = frappe.db.get_value("Department", {"department_name": department_value}, "name")
	if exact_name:
		return exact_name

	rows = frappe.db.sql(
		"""
		select name
		from `tabDepartment`
		where lower(ifnull(department_name, '')) = lower(%s)
		   or lower(name) = lower(%s)
		limit 2
		""",
		(department_value, department_value),
		as_dict=True,
	)
	if not rows:
		frappe.throw(f"Không tìm thấy Department cho Ban gửi đi: {department_value}.")
	if len(rows) > 1:
		frappe.throw(f"Ban gửi đi {department_value} đang map ra nhiều Department.")
	return rows[0]["name"]


def _resolve_incoming_document(value: str) -> str:
	value = value.strip()
	if frappe.db.exists("VNT Document Management", value):
		vnt_type = frappe.db.get_value("VNT Document Management", value, "vnt_type")
		if vnt_type != "Công văn đến":
			frappe.throw(f"Văn bản {value} không phải Công văn đến.")
		return value

	rows = frappe.get_all(
		"VNT Document Management",
		filters={"vnt_type": "Công văn đến", "reference_number": value},
		fields=["name"],
		limit_page_length=2,
	)
	if not rows:
		frappe.throw(f"Không tìm thấy Công văn đến tương ứng: {value}.")
	if len(rows) > 1:
		frappe.throw(
			f"Giá trị {value} đang khớp nhiều Công văn đến. Hãy truyền trực tiếp name của chứng từ."
		)
	return rows[0]["name"]


def _require_text(payload: Mapping[str, object], label: str, *keys: str) -> str:
	value = _first_present(payload, *keys)
	if value is None:
		frappe.throw(f"Thiếu tham số bắt buộc: {label}.")

	text = str(value).strip()
	if not text:
		frappe.throw(f"Tham số {label} không được để trống.")
	return text


def _require_date(payload: Mapping[str, object], label: str, *keys: str) -> str:
	value = _first_present(payload, *keys)
	if value is None:
		frappe.throw(f"Thiếu tham số bắt buộc: {label}.")
	return _normalize_date(value, label)


def _optional_date(payload: Mapping[str, object], *keys: str) -> str | None:
	value = _first_present(payload, *keys)
	if value is None:
		return None
	return _normalize_date(value, "Ngày")


def _normalize_date(value: object, label: str) -> str:
	try:
		return getdate(value).isoformat()
	except Exception:
		frappe.throw(f"{label} không đúng định dạng ngày hợp lệ.")


def _first_present(payload: Mapping[str, object], *keys: str):
	for key in keys:
		if key not in payload:
			continue
		value = payload.get(key)
		if value is None:
			continue
		if isinstance(value, str) and not value.strip():
			continue
		return value
	return None


def _extract_auth_context() -> dict[str, object]:
	header = (frappe.get_request_header("Authorization") or "").strip()
	auth_type = ""
	api_key = ""
	api_secret = ""
	token = ""

	if header:
		auth_type, _, token = header.partition(" ")
		auth_type = auth_type.strip().lower()
		token = token.strip()
		if auth_type == "token":
			api_key, _, api_secret = token.partition(":")
		elif auth_type == "basic" and token:
			try:
				decoded = frappe.safe_decode(base64.b64decode(token))
				api_key, _, api_secret = decoded.partition(":")
			except (binascii.Error, ValueError):
				pass

	return {
		"authorization_header": header,
		"auth_type": auth_type,
		"auth_source": frappe.get_request_header("Frappe-Authorization-Source") or DEFAULT_AUTH_SOURCE,
		"api_key": api_key,
		"api_secret": api_secret,
		"api_key_prefix": _api_key_prefix(api_key),
		"api_user": None,
	}


def _insert_api_log(
	*,
	status: str,
	operation: str,
	endpoint: str,
	request_payload: Mapping[str, object],
	response_payload: Mapping[str, object] | None,
	auth_context: Mapping[str, object],
	attachment: tuple[str, bytes] | None,
	doc,
	duration_ms: int,
	error_text: str | None = None,
	exc: Exception | None = None,
	commit: bool = False,
):
	if not frappe.db.exists("DocType", LOG_DOCTYPE):
		return

	try:
		log_doc = frappe.new_doc(LOG_DOCTYPE)
		log_doc.update(
			{
				"requested_at": frappe.utils.now_datetime(),
				"endpoint": endpoint,
				"operation": operation,
				"request_method": getattr(getattr(frappe.local, "request", None), "method", None) or "POST",
				"status": status,
				"http_status": 200 if status == "Success" else _failure_http_status(exc),
				"api_user": auth_context.get("api_user"),
				"auth_source": auth_context.get("auth_source"),
				"api_key_prefix": auth_context.get("api_key_prefix"),
				"remote_addr": getattr(getattr(frappe.local, "request", None), "remote_addr", None),
				"file_name": attachment[0] if attachment else None,
				"file_size": len(attachment[1]) if attachment else 0,
				"duration_ms": duration_ms,
				"request_payload": frappe.as_json(_sanitize_request_payload(request_payload), indent=2),
				"response_payload": frappe.as_json(response_payload or {}, indent=2),
				"error": error_text,
				"document": getattr(doc, "name", None),
				"reference_number": getattr(doc, "reference_number", None)
				or (response_payload or {}).get("reference_number"),
			}
		)
		log_doc.insert(ignore_permissions=True)
		if commit:
			frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), _("VNT API Integration Log Error"))


def _sanitize_request_payload(payload: Mapping[str, object]) -> dict[str, object]:
	sanitized = dict(payload or {})
	for field in PDF_BASE64_FIELDS:
		if field in sanitized and sanitized[field]:
			content = str(sanitized[field])
			sanitized[field] = f"[base64 omitted: {len(content)} chars]"
	for field in PDF_FILE_FIELDS:
		if field in sanitized and sanitized[field]:
			sanitized[field] = "[file handled via multipart upload]"
	return sanitized


def _duration_ms(started: float) -> int:
	return int((time.perf_counter() - started) * 1000)


def _safe_error_message(exc: Exception) -> str:
	if isinstance(exc, (AuthenticationError, PermissionError)):
		return str(exc)
	message = frappe.message_log[-1].get("message") if getattr(frappe.local, "message_log", None) else None
	return frappe.utils.strip_html(message) if message else str(exc)


def _failure_http_status(exc: Exception | None) -> int:
	if isinstance(exc, AuthenticationError):
		return 401
	if isinstance(exc, PermissionError):
		return 403
	return 500


def _api_key_prefix(api_key: str | None) -> str | None:
	api_key = (api_key or "").strip()
	if not api_key:
		return None
	return api_key[:6]

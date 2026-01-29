# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.utils import cint, cstr, flt, get_url_to_form
from frappe.utils.data import escape_html
from vinatex.patches.utils.rocket_chat import send_rocket_message

_FOLLOWER_EMPLOYEE = "VGT00175"


class VNTExternalProducts(Document):
	"""Form đăng ký sản phẩm đối ngoại."""

	def before_insert(self):
		_set_default_follower(self)
		_set_default_list_item_type(self)
		_apply_is_all_flag(self)

	def validate(self):
		_set_default_follower(self)
		_set_default_list_item_type(self)
		_apply_is_all_flag(self)
		_sync_inventory_export_flags(self)

	def on_update(self):
		# Chỉ xử lý khi trạng thái workflow đổi
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)

	def on_update_after_submit(self):
		_apply_is_all_flag(self, persist=True)
		_sync_inventory_export_flags(self)


def _handle_state_transition(doc: Document):
	"""Đồng bộ thông báo, ToDo theo từng bước workflow."""
	prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)

	approver_user = get_employee_user_id(doc.get("approver"))
	approver_lv2 = doc.get("approver_lv2")
	approver_lv2_user = get_employee_user_id(approver_lv2)
	has_second_level = bool(approver_lv2)

	if curr_state == "Chờ lãnh đạo duyệt" and prev_state == "Mới tạo":
		if _try_skip_first_level(doc, approver_user):
			return
		_notify_to_approver(doc, approver_user)

	if curr_state == "Chờ lãnh đạo tập đoàn duyệt" and prev_state == "Chờ lãnh đạo duyệt":
		_check_state_to_close_todo(doc, approver_user)
		_notify_to_approver_lv2(doc, approver_lv2_user)
		_notify_requester(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đang chờ Lãnh đạo Tập đoàn duyệt."))

	if curr_state == "Đã duyệt" and prev_state == "Chờ lãnh đạo duyệt":
		_check_state_to_close_todo(doc, approver_user)
		if not has_second_level:
			_notify_requester(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đã được lãnh đạo duyệt."))
			_notify_follower(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đã được lãnh đạo duyệt."))
		_record_inventory_movements(doc)

	if curr_state == "Đã duyệt" and prev_state == "Chờ Lãnh đạo Tập đoàn duyệt":
		_check_state_to_close_todo(doc, approver_lv2_user)
		_notify_requester(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đã được Lãnh đạo Tập đoàn duyệt."))
		_notify_follower_prepare_gift(doc)
		_record_inventory_movements(doc)

	if prev_state == "Chờ lãnh đạo duyệt" and curr_state == "Từ chối":
		_check_state_to_close_todo(doc, approver_user)
		_notify_requester(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đã bị lãnh đạo từ chối."))
		_notify_follower(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đã bị lãnh đạo từ chối."))

	if prev_state == "Chờ Lãnh đạo Tập đoàn duyệt" and curr_state == "Từ chối":
		_check_state_to_close_todo(doc, approver_lv2_user)
		_notify_requester(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đã bị Lãnh đạo Tập đoàn từ chối."))
		_notify_follower(doc, _("Phiếu đăng ký sản phẩm đối ngoại của {0} đã bị Lãnh đạo Tập đoàn từ chối."))

	if curr_state == "Từ chối":
		_check_state_to_close_todo(doc, approver_user)
		_check_state_to_close_todo(doc, approver_lv2_user)


def _notify_to_approver(doc: Document, user: str | None):
	"""Nhắc lãnh đạo cấp 1 duyệt và tạo ToDo."""
	if not user:
		return
	subject = _("Phiếu đăng ký sản phẩm đối ngoại của {0} đang chờ duyệt.").format(doc.employee_name or _("(không rõ)"))
	_notify_users(doc, [user], subject)
	ensure_todo(doc, user)


def _notify_to_approver_lv2(doc: Document, user: str | None):
	"""Nhắc lãnh đạo tập đoàn duyệt và tạo ToDo."""
	if not user:
		return
	subject = _("Phiếu đăng ký sản phẩm đối ngoại của {0} đang chờ lãnh đạo tập đoàn duyệt.").format(doc.employee_name or _("(không rõ)"))
	_notify_users(doc, [user], subject)
	ensure_todo(doc, user)


def _notify_requester(doc: Document, template: str):
	"""Gửi thông báo cho người tạo phiếu/nhân viên."""
	users = _collect_requester_users(doc)
	if not users:
		return
	subject = template.format(doc.employee_name or _("(không rõ)"))
	_notify_users(doc, users, subject)


def _notify_follower(doc: Document, template: str):
	"""Gửi thông báo cho người theo dõi khi cần."""
	user = get_employee_user_id(doc.get("follower"))
	if not user:
		return
	subject = template.format(doc.employee_name or _("(không rõ)"))
	_notify_users(doc, [user], subject)


def _notify_follower_prepare_gift(doc: Document):
	"""Nhắc người theo dõi chuẩn bị quà sau khi lãnh đạo tập đoàn duyệt."""
	user = get_employee_user_id(doc.get("follower"))
	if not user:
		return
	item_summary = _format_export_items(doc)
	subject = _("Chuẩn bị sản phẩm đối ngoại cho {0}: {1}").format(
		doc.employee_name or _("(không rõ)"),
		item_summary,
	)
	_notify_users(doc, [user], subject)


def _notify_users(doc: Document, users: list[str] | set[str], subject: str):
	"""Wrapper tạo notification log và thông báo Rocket.Chat."""
	unique_users = {u for u in users if u}
	if not unique_users:
		return
	make_notification_logs({
		"type": "Alert",
		"subject": subject,
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, list(unique_users))
	url = get_url_to_form(doc.doctype, doc.name)
	teams_message = "<br>".join([
		"<b>🔔 Thông báo</b>",
		f"<b>{escape_html(subject)}</b>",
		f'<a href="{escape_html(url)}">Xem chi tiết</a>',
	])
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=list(unique_users),
		content_type="html",
		linkify=False,
		message=teams_message,
	)
	send_rocket_message(
		to_users=list(unique_users),
		title=":bell: Thông báo",
		message=subject,
		link=url,
	)


def _collect_requester_users(doc: Document) -> set[str]:
	"""Lấy danh sách user cần báo cho người tạo phiếu."""
	users: set[str] = set()
	employee_user = get_employee_user_id(doc.get("employee"))
	if employee_user:
		users.add(employee_user)
	if doc.owner:
		users.add(doc.owner)
	return users


def ensure_todo(doc: Document, user: str | None):
	"""Tạo ToDo duyệt nếu chưa có."""
	if not user:
		return
	if frappe.db.exists("ToDo", {
		"reference_type": doc.doctype,
		"reference_name": doc.name,
		"allocated_to": user,
		"status": ["!=", "Cancelled"],
	}):
		return
	description = _("Duyệt đăng ký sản phẩm đối ngoại của {0}.").format(doc.employee_name or _("(không rõ)"))
	new_todo = frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = "Medium"
	new_todo.status = "Open"
	new_todo.insert(ignore_permissions=True)
	frappe.db.commit()


def _check_state_to_close_todo(doc: Document, user: str | None):
	"""Đóng ToDo mở tương ứng với trạng thái hiện tại."""
	if not user:
		return
	names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"allocated_to": user,
			"status": ["!=", "Cancelled"],
		},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("ToDo", name, "status", "Closed", update_modified=False)


def _get_prev_and_curr_workflow_state(doc: Document) -> tuple[str | None, str]:
	"""Lấy trạng thái workflow trước và sau khi lưu."""
	prev_state = None
	try:
		before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
		if before:
			prev_state = (before.get("workflow_state") or "").strip()
	except Exception:
		prev_state = None

	if not prev_state and doc.get("name"):
		try:
			prev_state = (frappe.db.get_value(doc.doctype, doc.name, "workflow_state") or "").strip()
		except Exception:
			prev_state = None

	curr_state = (doc.get("workflow_state") or "").strip()
	return prev_state, curr_state


def _set_default_follower(doc: Document):
	"""Gán cố định người theo dõi là nhân sự phụ trách quà tặng."""
	doc.follower = _FOLLOWER_EMPLOYEE
	emp_name = frappe.db.get_value("Employee", _FOLLOWER_EMPLOYEE, "employee_name") or ""
	doc.follower_name = emp_name


def _set_default_list_item_type(doc: Document):
	"""Mặc định loại giao dịch của bảng con là Xuất."""
	for row in doc.get("list_items") or []:
		row_type = (row.get("type") or "").strip()
		if not row_type:
			row.type = "Xuất"


def _apply_is_all_flag(doc: Document, *, persist: bool = False):
	"""Nếu bật is_all thì đánh dấu tất cả dòng đã xuất."""
	if not cint(doc.get("is_all")):
		return
	for row in doc.get("list_items") or []:
		row.is_export = 1
		if persist and row.get("name"):
			frappe.db.set_value(row.doctype, row.name, "is_export", 1, update_modified=False)


def _record_inventory_movements(doc: Document):
	"""Đẩy phát sinh được duyệt sang danh mục tồn kho."""
	child_rows = [row for row in doc.get("list_items") or [] if row.get("item_code")]
	if not child_rows:
		return

	doc_name = cstr(doc.name)
	rows_by_item = defaultdict(list)
	for row in child_rows:
		item_name = row.get("item_code")
		qty = flt(row.get("qty"))
		if not item_name or not qty:
			continue
		rows_by_item[item_name].append((row, qty))

	for item_name, entries in rows_by_item.items():
		try:
			item_doc = frappe.get_doc("VNT External Products List", item_name)
		except frappe.DoesNotExistError:
			continue

		needs_save = False
		for row, qty in entries:
			child_identifier = _build_inventory_child_name(doc_name, row.get("name"))
			if not child_identifier:
				continue
			child_values = {
				"item_code": item_name,
				"item_name": row.get("item_name") or item_doc.item_name,
				"unit": row.get("unit") or item_doc.unit,
				"qty": qty,
				"type": (row.get("type") or "Xuất").strip() or "Xuất",
				"is_export": cint(row.get("is_export")),
			}
			if frappe.db.exists("VNT External Products Items List", child_identifier):
				frappe.db.set_value("VNT External Products Items List", child_identifier, child_values, update_modified=False)
				continue

			child = item_doc.append("list_items", {})
			child.name = child_identifier
			child.item_code = child_values["item_code"]
			child.item_name = child_values["item_name"]
			child.unit = child_values["unit"]
			child.qty = child_values["qty"]
			child.type = child_values["type"]
			child.is_export = child_values["is_export"]
			needs_save = True

		if needs_save:
			item_doc.save(ignore_permissions=True)


def _format_export_items(doc: Document) -> str:
	"""Tạo mô tả ngắn gọn danh sách sản phẩm cần chuẩn bị."""
	entries: list[str] = []
	for row in doc.get("list_items") or []:
		item_name = (row.get("item_name") or row.get("item_code") or "").strip()
		if not item_name:
			continue
		qty = flt(row.get("qty"))
		unit = (row.get("unit") or "").strip()
		if qty:
			qty_str = f"{qty:g}"
			if unit:
				qty_str = f"{qty_str} {unit}"
			entries.append(f"{item_name} ({qty_str})")
		else:
			entries.append(item_name)
	return ", ".join(entries) if entries else _("(không có sản phẩm)")


def _sync_inventory_export_flags(doc: Document):
	"""Đồng bộ cờ is_export sang bảng tồn kho sau khi doc đã duyệt."""
	if doc.docstatus != 1:
		return
	doc_name = cstr(doc.name)
	for row in doc.get("list_items") or []:
		child_identifier = _build_inventory_child_name(doc_name, row.get("name"))
		if not child_identifier:
			continue
		if not frappe.db.exists("VNT External Products Items List", child_identifier):
			continue
	frappe.db.set_value(
		"VNT External Products Items List",
		child_identifier,
		"is_export",
		cint(row.get("is_export")),
		update_modified=False,
	)


def _build_inventory_child_name(doc_name: str | None, child_name: str | None) -> str | None:
	if not doc_name or not child_name:
		return None
	return f"{cstr(doc_name)}-{cstr(child_name)}"


def get_employee_user_id(employee_name: str | None) -> str | None:
	"""Đổi mã Employee sang user id."""
	if not employee_name:
		return None
	return frappe.db.get_value("Employee", employee_name, "user_id")


def _should_skip_first_level(doc: Document) -> bool:
	"""Kiểm tra nếu người đề xuất cũng là người duyệt cấp 1."""
	employee = (doc.get("employee") or "").strip()
	approver = (doc.get("approver") or "").strip()
	if employee and approver and employee == approver:
		return True

	employee_name = (doc.get("employee_name") or "").strip().lower()
	approver_name = (doc.get("approver_name") or "").strip().lower()
	return bool(employee_name and approver_name and employee_name == approver_name)


def _try_skip_first_level(doc: Document, approver_user: str | None) -> bool:
	"""Tự động bỏ qua bước duyệt cấp 1 nếu người tạo trùng người duyệt (với các trường hợp người tạo là trưởng ban)
	  - Ai trưởng ban lại tạo cái này cơ chứ =="""
	if not _should_skip_first_level(doc):
		return False
	if not approver_user:
		return False

	current_user = frappe.session.user
	try:
		frappe.set_user(approver_user)
		apply_workflow(doc, "Duyệt")
		return True
	except Exception:
		frappe.log_error(
			title="VNT External Products: skip cấp 1 thất bại",
			message=frappe.get_traceback(),
		)
		return False
	finally:
		frappe.set_user(current_user)


@frappe.whitelist()
def get_employee_name(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "name", as_dict=True)
	return employee_doc.name if employee_doc else ""


@frappe.whitelist()
def get_reports_to(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "department", as_dict=True)
	if not employee_doc:
		return
	approver = frappe.get_value("Department Approver", {"parent": employee_doc.department, "custom_level_1": True}, "approver", as_dict=True)
	if approver:
		approver_emp = frappe.get_value("Employee", {"user_id": approver.approver}, ["name", "employee_name"])
	return approver_emp if approver else ""

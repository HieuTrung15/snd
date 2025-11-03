# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs


class VNTCarRegistration(Document):
	def on_update(self):
		# chuyển sang theo dõi workflow_state
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)

	
def _handle_state_transition(doc: Document):
	# xử lý chuyển trạng thái
	prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)
	# thông báo cho lãnh đạo
	approver = doc.get("approver")
	approver_user = get_employee_user_id(approver)
	# thông báo cho lãnh đạo tập đoàn
	approver_lv2 = doc.get("approver_lv2")
	approver_user_lv2 = get_employee_user_id(approver_lv2)
	if curr_state == "Chờ lãnh đạo duyệt" and prev_state == "Mới tạo":
		_notify_to_approver(doc, user=approver_user)
	if curr_state == "Đã duyệt" and prev_state == "Chờ lãnh đạo duyệt" or \
		curr_state == "Chờ lãnh đạo tập đoàn duyệt" and prev_state == "Chờ lãnh đạo duyệt":
		_check_state_to_close_todo(doc, user=approver_user)
	if curr_state == "Đã duyệt" and prev_state == "Chờ lãnh đạo tập đoàn duyệt":
		_check_state_to_close_todo(doc, user=approver_user_lv2)
	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		_notify_to_approver_2(doc, user=approver_user_lv2)
	if curr_state == 'Từ chối':
		_check_state_to_close_todo(doc, user=approver_user)
		_check_state_to_close_todo(doc, user=approver_user_lv2)

	# thông báo cho employee
	employee_user = doc.get("employee")
	approver_user = get_employee_user_id(employee_user)
	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Đã duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký xe của {0} đã được lãnh đạo duyệt").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký xe của {0} đang chờ lãnh đạo tập đoàn duyệt").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Đã duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký xe của {0} đã được lãnh đạo tập đoàn duyệt").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu đăng ký xe của {0} đã bị lãnh đạo từ chối.").format(doc.employee_name or _("(không rõ)")),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, [approver_user])

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu đăng ký xe của {0} đã bị lãnh đạo tập đoàn từ chối.").format(doc.employee_name or _("(không rõ)")),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, [approver_user])
		

def _notify_to_approver(doc: Document, user: str | None):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo duyệt'."""
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký xe của {0} đang chờ lãnh đạo duyệt.").format(doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		"subject": _('Duyệt đăng ký xe của {0}').format(doc.employee_name or _("(không rõ)")),
	}, [user])
	# tạo todo cho người duyệt
	ensure_todo(doc, user)


def _notify_to_approver_2(doc: Document, user: str | None):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo tập đoàn duyệt'."""
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký xe của {0} đang chờ lãnh đạo tập đoàn duyệt.").format(doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
		"subject": _('Duyệt đăng ký xe của {0}').format(doc.employee_name or _("(không rõ)")),
	}, [user])
	# tạo todo cho người duyệt
	ensure_todo(doc, user)


def get_employee_user_id(employee_name: str) -> str | None:
    if not employee_name:
        return None
    return frappe.db.get_value("Employee", employee_name, "user_id")


def ensure_todo(doc: Document, user: str):
	if not user:
		return
	if frappe.db.exists("ToDo", {
		"reference_type": doc.doctype,
		"reference_name": doc.name,
		"allocated_to": user,
		"status": ["!=", "Cancelled"],
	}):
		return
	description = _('Duyệt đăng ký xe của {0}').format(doc.employee_name or _("(không rõ)"))
	new_todo =  frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = "Medium"
	new_todo.status = "Open"
	new_todo.insert(ignore_permissions=True)
	frappe.db.commit()


def _check_state_to_close_todo(doc: Document, user: str):
    """Close open ToDos for the current approver on this document."""
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
    for n in names:
      frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


def _get_prev_and_curr_workflow_state(doc: Document) -> tuple[str | None, str]:
	"""Trả về (previous_state, current_state) an toàn.
	- Ưu tiên lấy previous từ get_doc_before_save() nếu có.
	- Fallback lấy từ DB nếu chưa có trước đó (hoặc không ở on_update).
	"""
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

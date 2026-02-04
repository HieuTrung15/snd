# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.utils import nowdate, get_url_to_form, cstr, formatdate, format_time
from frappe import _
from frappe.model.document import Document
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from vinatex.patches.utils.rocket_chat import send_rocket_message
from vinatex.patches.utils.rocket_chat import send_rocket_message_async as send_rocket_message
from frappe.model.workflow import apply_workflow
from vinatex.integrations.teams_graph import notify_user


class VNTCarRegistration(Document):
	def validate(self):
		# validate nếu danh sách nhân sự trùng ngày giờ đăng ký xe
		_validate_employee_schedule(self)
		_set_people_count(self)

	def on_update(self):
		# chuyển sang theo dõi workflow_state
		if self.has_value_changed("workflow_state"):
			_handle_state_transition(self)
		_sync_business_trip_transportation(self)

	
def _handle_state_transition(doc: Document):
	# xử lý chuyển trạng thái
	prev_state, curr_state = _get_prev_and_curr_workflow_state(doc)
	# thông báo cho lãnh đạo
	approver = doc.get("approver")
	approver_user = get_employee_user_id(approver)
	# thông báo cho lãnh đạo tập đoàn
	approver_lv2 = doc.get("approver_name_lv2")
	approver_user_lv2 = get_employee_user_id(approver_lv2)
	if curr_state == "Chờ lãnh đạo duyệt" and prev_state == "Mới tạo":
		_notify_to_approver(doc, user=approver_user)
	if curr_state == "Chờ lãnh đạo tập đoàn duyệt" and prev_state == "Mới tạo":
		_notify_to_approver_2(doc, user=approver_user_lv2)
	if curr_state == "Đã duyệt" and prev_state == "Chờ lãnh đạo duyệt":
		_check_state_to_close_todo(doc, user=approver_user)
		_notify_to_user_receive(doc)
		_notify_to_office_manager(doc)
		# _notify_to_employee_list(doc)
	if curr_state == "Chờ lãnh đạo tập đoàn duyệt" and prev_state == "Chờ lãnh đạo duyệt":
		_check_state_to_close_todo(doc, user=approver_user)
	if curr_state == "Đã duyệt" and prev_state == "Chờ lãnh đạo tập đoàn duyệt":
		_check_state_to_close_todo(doc, user=approver_user_lv2)
		_notify_to_user_receive(doc)
		_notify_to_office_manager(doc)
		# _notify_to_employee_list(doc)
	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		_notify_to_approver_2(doc, user=approver_user_lv2)
		# _notify_to_approver_2(doc)
	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Đã duyệt':
		# _notify_to_employee(doc, "duyệt")
		pass
	if (prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Từ chối'):
		# _notify_to_employee(doc, "từ chối")
		pass

	if prev_state == "Mới tạo" and curr_state == "Đã duyệt":
		_notify_to_user_receive(doc)
	
	if curr_state == 'Từ chối':
		_check_state_to_close_todo(doc, user=approver_user)
		_check_state_to_close_todo(doc, user=approver_user_lv2)

	# thêm trường hợp các trưởng ban tạo < 40 thì duyệt luôn, các ld cũng thế
	# đã thêm transition trong wf
	if not (doc.employee and doc.approver and doc.approver_lv2):
		return

	# thông báo cho employee
	employee_user = doc.get("employee")
	approver_user = get_employee_user_id(employee_user)
	url = get_url_to_form(doc.doctype, doc.name)

	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Đã duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký xe của {0} đã được lãnh đạo phê duyệt.").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký xe của {0} đã được lãnh đạo phê duyệt.").format(doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=[approver_user],
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký xe của {0} đã được lãnh đạo phê duyệt.<br>"
				"<a href=\"{1}\">Xem chi tiết</a>"
			).format(
				doc.employee_name or _("(không rõ)"),
				url
			),
		)


	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Chờ lãnh đạo tập đoàn duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký xe của {0} đang chờ lãnh đạo tập đoàn phê duyệt.").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký xe của {0} đang chờ lãnh đạo tập đoàn phê duyệt.").format(doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=[approver_user],
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký xe của {0} đang chờ lãnh đạo tập đoàn phê duyệt.<br>"
				"<a href=\"{1}\">Xem chi tiết</a>"
			).format(
				doc.employee_name or _("(không rõ)"),
				url
			),
		)

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Đã duyệt':
		make_notification_logs({
			"type": "Alert",
			"subject": _("Phiếu đăng ký xe của {0} đã được lãnh đạo tập đoàn duyệt.").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký xe của {0} đã được lãnh đạo tập đoàn phê duyệt.").format(doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=[approver_user],
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký xe của {0} đã được lãnh đạo tập đoàn phê duyệt.<br>"
				"<a href=\"{1}\">Xem chi tiết</a>"
			).format(
				doc.employee_name or _("(không rõ)"),
				url
			),
		)


	if prev_state == 'Chờ lãnh đạo duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu đăng ký xe của {0} đã bị lãnh đạo từ chối.").format(doc.employee_name or _("(không rõ)")),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký xe của {0} đã bị lãnh đạo từ chối.").format(doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=[approver_user],
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký xe của {0} đã bị lãnh đạo từ chối.<br>"
				"<a href=\"{1}\">Xem chi tiết</a>"
			).format(
				doc.employee_name or _("(không rõ)"),
				url
			),
		)

	if prev_state == 'Chờ lãnh đạo tập đoàn duyệt' and curr_state == 'Từ chối':
		make_notification_logs({
        "type": "Alert",
        "subject": _("Phiếu đăng ký xe của {0} đã bị lãnh đạo tập đoàn từ chối.").format(doc.employee_name or _("(không rõ)")),
        "document_type": doc.doctype,
        "document_name": doc.name,
    }, [approver_user])
		send_rocket_message(
			to_users=approver_user,
			title=":bell: Thông báo",
			message=_("Phiếu đăng ký xe của {0} đã bị lãnh đạo tập đoàn từ chối.").format(doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=30,
			is_async=True,
			upn_or_email=[approver_user],
			content_type="html",
			linkify=False,
			message=_(
				"🔔 Phiếu đăng ký xe của {0} đã bị lãnh đạo tập đoàn từ chối.<br>"
				"<a href=\"{1}\">Xem chi tiết</a>"
			).format(
				doc.employee_name or _("(không rõ)"),
				url
			),
		)


# gửi thông báo đến người quản lý văn phòng
def _notify_to_office_manager(doc: Document):
	"""Gửi thông báo đến những members trong User Group 'Nhận thông báo đăng ký xin xe' khi đơn được duyệt."""
	user_group_name = "Nhận thông báo đăng ký xin xe"
	url = get_url_to_form(doc.doctype, doc.name)
	user_list = frappe.get_all(
		"User Group Member",
		filters={"parent": user_group_name},
		pluck="user",
	)
	if not user_list:
		return
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký xe của {0} ban {1} đã được duyệt.").format(doc.employee_name or _("(không rõ)"), doc.department or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, user_list)
	send_rocket_message(
		to_users=user_list,
		title=":bell: Thông báo",
		message=_("Phiếu đăng ký xe của {0} ban {1} đã được duyệt.").format(doc.employee_name or _("(không rõ)"), doc.department or _("(không rõ)")),
		link=get_url_to_form(doc.doctype, doc.name)
	)
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=user_list,
		content_type="html",
		linkify=False,
		message=_(
			"🔔 Phiếu đăng ký xe của {0} ban {1} đã được duyệt.<br>"
		).format(
			doc.employee_name or _("(không rõ)"),
			doc.department or _("(không rõ)"),
		),
	)


# gửi thông báo đến emp tham gia chuyến xe
def _notify_to_employee_list(doc):
	"""Gửi thông báo đến list nhân viên(list_emp) khi đơn được duyệt."""
	list_emp = doc.get("list_emp")
	if not list_emp:
		return
	for emp in list_emp:
		employee_user = get_employee_user_id(emp.employee)
		if not employee_user:
			continue
		make_notification_logs({
			"type": "Alert",
			"subject": _("Bạn đi cùng chuyến xe của {0}. Vui lòng kiểm tra thông tin chi tiết.").format(doc.employee_name or _("(không rõ)")),
			"document_type": doc.doctype,
			"document_name": doc.name,
		}, [employee_user])
		send_rocket_message(
			to_users=employee_user,
			title=":bell: Thông báo",
			message=_("Bạn đi cùng chuyến xe của {0}. Vui lòng kiểm tra thông tin chi tiết.").format(doc.employee_name or _("(không rõ)")),
			link=get_url_to_form(doc.doctype, doc.name)
		)


# gửi thông báo đến người điều xe
def _notify_to_user_receive(doc: Document):
	"""Gửi thông báo đến những members trong User Group 'Nhận thông báo điều xe' khi đơn được duyệt.
		Tạo bản ghi VNT Vehicle Control để người điều xe vào điền trong bản ghi này
	"""
	# tạo bản ghi mới trong vnt vehicle control
	user_group_name = "Nhận thông báo điều xe"
	user_list = frappe.get_all(
		"User Group Member",
		filters={"parent": user_group_name},
		pluck="user",
	)
	employee_user = frappe.get_value('User', {'name': user_list[0]}, 'full_name')
	items = doc.get("items") or []
	if items:
		vehicle_control = frappe.new_doc("VNT Vehicle Control")
		vehicle_control.employee_name = employee_user
		vehicle_control.date = nowdate()
		vehicle_control.employee = doc.employee_name
		vehicle_control.id_parent = doc.name
		for item in items:
			vehicle_control.append(
				"items",
				{
					"employee_name": doc.employee_name,
					"start": item.start,
					"end": item.end,
					"time": item.time,
					"date": item.date,
					"id_parent": doc.name,
					"id_child": item.name
				},
			)
		vehicle_control.insert(ignore_permissions=True)
		if vehicle_control:
			url = get_url_to_form("VNT Vehicle Control", vehicle_control.name)
			make_notification_logs({
				"type": "Alert",
				"subject": _("Điều xe cho phiếu đăng ký xe của {0} ban {1}.").format(doc.employee_name or _("(không rõ)"), doc.department or _("(không rõ)")),
				"document_type": 'VNT Vehicle Control',
				"document_name": vehicle_control.name,
			}, user_list)
			# send_rocket_message(
			# 	to_users=user_list,
			# 	title=":bell: Thông báo",
			# 	message=_("Điều xe cho phiếu đăng ký xe của {0}.").format(doc.employee_name or _("(không rõ)")),
			# 	link=get_url_to_form(doc.doctype, doc.name)
			# )
			frappe.enqueue(
				"vinatex.integrations.teams_graph.notify_user",
				queue="short",
				timeout=30,
				is_async=True,
				upn_or_email=user_list,
				content_type="html",
				linkify=False,
				message=_(
					"🔔 Điều xe cho phiếu đăng ký xe của {0} ban {1}.<br>"
					"<a href=\"{2}\">Xem chi tiết</a>"
				).format(
					doc.employee_name or _("(không rõ)"),
					doc.department or _("(không rõ)"),
					url
				),
			)
			new_todo =  frappe.new_doc("ToDo")
			new_todo.description = _("Điều xe cho phiếu đăng ký xe của {0} ban {1}.").format(doc.employee_name or _("(không rõ)"), doc.department or _("(không rõ)"))
			new_todo.allocated_to = user_list[0]
			new_todo.reference_type = 'VNT Vehicle Control'
			new_todo.reference_name = vehicle_control.name
			new_todo.priority = "Medium"
			new_todo.status = "Open"
			new_todo.save(ignore_permissions=True)
			frappe.db.commit()


def _sync_business_trip_transportation(doc: Document):
	if doc.docstatus != 1:
		return

	business_trip = doc.get("business_trip")
	if not business_trip:
		return

	try:
		trip_doc = frappe.get_doc("VNT Business Trip Request", business_trip)
	except frappe.DoesNotExistError:
		return

	transportation = trip_doc.get("transportation") or []
	if not transportation:
		return

	transport_map: dict[tuple[str, str, str, str], list] = {}
	for row in transportation:
		key = (
			row.start,
			row.end,
			row.date,
			row.time,
		)
		transport_map.setdefault(key, []).append(row)

	for item in doc.get("items") or []:
		driver = item.get("lái_xe")
		if not driver:
			continue

		key = (
			item.get("start"),
			item.get("end"),
			item.get("date"),
			item.get("time"),
		)
		rows = transport_map.get(key)
		if not rows:
			continue

		transport_row = rows.pop(0)
		if transport_row.driver != driver:
			frappe.db.set_value(
				"VNT Business Trip Request Transportation",
				transport_row.name,
				"driver",
				driver,
			)
			transport_row.driver = driver


def _validate_employee_schedule(doc: Document):
	list_emp = doc.get("list_emp") or []
	items = [item for item in (doc.get("items") or []) if item.date]
	if not list_emp or not items:
		return

	seen: set[str] = set()
	employees: list[str] = []
	for row in list_emp:
		employee = row.get("employee")
		if not employee:
			continue
		if employee in seen:
			frappe.throw(
				_("Nhân sự {0} đã được thêm vào danh sách. Vui lòng không chọn trùng.").format(
					frappe.bold(employee)
				)
			)
		seen.add(employee)
		employees.append(employee)

	if not employees:
		return

	current_name = doc.name if doc.name and not doc.is_new() else None

	for employee in employees:
		for item in items:
			conflicts = frappe.db.sql(
				"""
				SELECT DISTINCT reg.name, itm.date, itm.time
				FROM `tabVNT Car Registration` reg
				INNER JOIN `tabVNT Car Registration Employee` emp ON emp.parent = reg.name
				INNER JOIN `tabVNT Car Registration Item` itm ON itm.parent = reg.name
				WHERE reg.docstatus != 2
					AND reg.workflow_state = 'Đã hủy'
				  AND emp.employee = %(employee)s
				  AND itm.date = %(date)s
				  AND (%(time)s IS NULL OR itm.time IS NULL OR itm.time = %(time)s)
				  AND (%(current)s IS NULL OR reg.name != %(current)s)
				LIMIT 1
				""",
				{
					"employee": employee,
					"date": item.date,
					"time": item.time,
					"current": current_name,
				},
				as_dict=True,
			)
			if conflicts:
				conflict = conflicts[0]
				conflict_date = formatdate(conflict.date) if conflict.date else _("(không rõ)")
				conflict_time = format_time(conflict.time) if conflict.time else _("(không rõ)")
				frappe.throw(
					_("Nhân sự {0} đã có đăng ký xe {1} vào ngày {2} lúc {3}. Vui lòng chọn thời gian khác.").format(
						frappe.bold(employee),
						frappe.bold(conflict.name),
						conflict_date,
						conflict_time,
					)
				)


def _set_people_count(doc: Document):
	doc.people = len(doc.get("list_emp") or [])


def _notify_to_approver(doc: Document, user: str | None):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo duyệt'."""
	url = get_url_to_form(doc.doctype, doc.name)
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký xe của {0} đang chờ lãnh đạo duyệt.").format(doc.employee_name or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, [user])
	send_rocket_message(
		to_users=user,
		title=":bell: Thông báo",
		message= _("Phiếu đăng ký xe của {0} đang chờ lãnh đạo duyệt.").format(doc.employee_name or _("(không rõ)")),
		link=get_url_to_form(doc.doctype, doc.name)
	)
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=user,
		content_type="html",
		linkify=False,
		message=_(
			"🔔 Phiếu đăng ký xe của {0} đang chờ lãnh đạo duyệt.<br>"
			"<a href=\"{1}\">Xem chi tiết</a>"
		).format(
			doc.employee_name or _("(không rõ)"),
			url
		),
	)
	# tạo todo cho người duyệt
	ensure_todo(doc, user)


def _notify_to_approver_2(doc: Document, user: str | None):
	"""Gửi thông báo đến người duyệt khi đơn được chuyển sang trạng thái 'Chờ lãnh đạo tập đoàn duyệt'."""
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký xe của {0} ban {1} đang chờ lãnh đạo tập đoàn duyệt.").format(
			doc.employee_name or _("(không rõ)"), 
			doc.department or _("(không rõ)")),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, [user])
	send_rocket_message(
		to_users=user,
		title=":bell: Thông báo",
		message= _('Duyệt đăng ký xe của {0}.').format(doc.employee_name or _("(không rõ)")),
		link=get_url_to_form(doc.doctype, doc.name)
	)
	url = get_url_to_form(doc.doctype, doc.name)
	frappe.enqueue(
		"vinatex.integrations.teams_graph.notify_user",
		queue="short",
		timeout=30,
		is_async=True,
		upn_or_email=[user],
		content_type="html",
		linkify=False,
		message=_(
			"🔔 Phiếu đăng ký xe của {0} ban {1} đang chờ lãnh đạo tập đoàn duyệt.<br>"
			"<a href=\"{2}\">Xem chi tiết</a>"
		).format(
			doc.employee_name or _("(không rõ)"),
			doc.department or _("(không rõ)"),
			url
		),
	)
	# tạo todo cho người duyệt
	ensure_todo(doc, user)

def _notify_to_employee(doc: Document, status: str):
	"""Gửi thông báo đến list nhân viên(list_emp) khi đơn được duyệt hoặc từ chối."""
	# list_emp = doc.get("list_emp")
	# if not list_emp:
	# 	return
	# for emp in list_emp:
	employee_user = get_employee_user_id(doc.employee)
	if not employee_user:
		return
	make_notification_logs({
		"type": "Alert",
		"subject": _("Phiếu đăng ký xe của {0} đã {1}.").format(
			doc.employee_name or _("(không rõ)"),
			status,
		),
		"document_type": doc.doctype,
		"document_name": doc.name,
	}, [employee_user])
	send_rocket_message(
		to_users=employee_user,
		title=":bell: Thông báo",
		message=_("Phiếu đăng ký xe của {0} đã {1}.").format(doc.employee_name or _("(không rõ)"),status,),
		link=get_url_to_form(doc.doctype, doc.name)
	)
	# frappe.enqueue(
			# 	"vinatex.integrations.teams_graph.notify_user",
			# 	queue="short",
			# 	timeout=30,
			# 	is_async=True,
			# 	upn_or_email=user_list,
			# 	content_type="html",
			# 	linkify=False,
			# 	message=_(
			# 		"🔔 Điều xe cho phiếu đăng ký xe của {0}.<br>"
			# 		"<a href=\"{1}\">Xem chi tiết</a>"
			# 	).format(
			# 		doc.employee_name or _("(không rõ)"),
			# 		url
			# 	),
			# )

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

	description = _('Duyệt đăng ký xe của {0}.').format(doc.employee_name or _("(không rõ)"))
	new_todo =  frappe.new_doc("ToDo")
	new_todo.description = description
	new_todo.allocated_to = user
	new_todo.reference_type = doc.doctype
	new_todo.reference_name = doc.name
	new_todo.priority = "Medium"
	new_todo.status = "Open"
	new_todo.save(ignore_permissions=True)
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
def get_list_employee_name(name):
	return frappe.get_value("Employee", {"name": name}, 'employee_name')


@frappe.whitelist()
def get_employee_names(names: list[str] | str | None = None):
	if not names:
		return {}
	if isinstance(names, str):
		try:
			names = json.loads(names)
		except ValueError:
			names = [names]
	if not isinstance(names, (list, tuple, set)):
		return {}
	names = [n for n in names if n]
	if not names:
		return {}
	records = frappe.get_all(
		"Employee",
		filters={"name": ["in", names]},
		fields=["name", "employee_name"],
		limit_page_length=0,
	)
	return {rec.name: rec.employee_name for rec in records}


@frappe.whitelist()
def get_employee_name(user):
	employee_doc = frappe.get_value("Employee", {"user_id": user}, "name", as_dict=True)
	return employee_doc.name if employee_doc else ""


# Lấy employee_name từ employee để hiển thị tên approver 
@frappe.whitelist()
def get_employee_display_name(employee: str | None = None):
	if not employee:
		return ""
	return frappe.db.get_value("Employee", employee, "employee_name") or ""


@frappe.whitelist()
def get_reports_to(user):
	employee_doc = frappe.get_value(
		"Employee",
		{"user_id": user},
		["name", "employee_name", "department"],
		as_dict=True,
	)
	if not employee_doc:
		return ""

	approver_users = frappe.get_all(
		"Department Approver",
		filters={"parent": employee_doc.department, "custom_level_1": True},
		pluck="approver",
	) or []

	# Nếu người dùng hiện tại nằm trong danh sách approver thì trả đúng người đó
	matched_user = next((a for a in approver_users if a == user), None)
	target_user = matched_user or (approver_users[0] if approver_users else None)
	if target_user:
		approver_emp = frappe.get_value(
			"Employee",
			{"user_id": target_user},
			["name", "employee_name"],
			as_dict=True,
		)
		if approver_emp:
			return [approver_emp.get("name"), approver_emp.get("employee_name")]

	return employee_doc.name, employee_doc.employee_name


@frappe.whitelist()
def check_leave_approver_2(employee: str | None = None) -> bool:
	"""Kiểm tra nhân viên có user thuộc role 'Leave Approver 2' hay không."""
	if not employee:
		return False

	user_id = frappe.db.get_value("Employee", employee, "user_id")
	if not user_id:
		return False

	roles = frappe.get_roles(user_id)
	return "Leave Approver L2" in roles

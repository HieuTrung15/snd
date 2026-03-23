# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.utils import formatdate, get_url_to_form
from vinatex.patches.utils.rocket_chat import send_rocket_message


class VNTVehicleControl(Document):
	def on_update(self):
		required_rows = [
			row for row in (self.items or [])
			if row.id_parent and row.id_child
		]
		has_full_driver = bool(required_rows) and all(row.driver for row in required_rows)
		new_status = "Đã điều xe" if has_full_driver else "Chưa điều xe"

		if self.status != new_status:
			self.db_set("status", new_status, update_modified=False)
			self.status = new_status

		if not self.items:
			return

		registrations: dict[str, Document | None] = {}
		trip_mappings: dict[str, dict | None] = {}
		recipients: set[str] = set()
		creator: set[str] = set()
		trip_dates: set[str] = set()

		for row in self.items:
			if not (row.id_parent and row.id_child and row.driver):
				continue

			car = registrations.get(row.id_parent)
			if car is None:
				try:
					car = frappe.get_doc("VNT Car Registration", row.id_parent)
				except frappe.DoesNotExistError:
					car = None
				registrations[row.id_parent] = car

			if not car:
				continue

			frappe.db.set_value("VNT Car Registration Item", row.id_child, "driver", row.driver)
			frappe.db.set_value("VNT Car Registration Item", row.id_child, "phone", row.phone)
			frappe.db.set_value("VNT Car Registration Item", row.id_child, "car_id", row.car_id)

			car_item = next((item for item in (car.get("items") or []) if item.name == row.id_child), None)
			if car_item and car_item.date:
				trip_dates.add(car_item.date)

			for passenger in car.get("list_emp") or []:
				user = get_employee_user_id(passenger.employee)
				create_user = get_employee_user_id(car.get("employee"))
				if user:
					recipients.add(user)
					creator.add(create_user)

			trip_name = car.get("business_trip")
			if not trip_name or not car_item:
				continue

			mapping = trip_mappings.get(trip_name)
			if mapping is None:
				try:
					trip_doc = frappe.get_doc("VNT Business Trip Request", trip_name)
				except frappe.DoesNotExistError:
					trip_mappings[trip_name] = None
					continue
				mapping = {}
				for transport in trip_doc.get("transportation") or []:
					key = (transport.start, transport.end, transport.date, transport.time)
					mapping.setdefault(key, []).append(transport)
				trip_mappings[trip_name] = mapping

			if not mapping:
				continue

			key = (car_item.start, car_item.end, car_item.date, car_item.time)
			candidates = mapping.get(key)
			if not candidates:
				continue

			transport_row = candidates.pop(0)
			if transport_row.driver != row.driver:
				frappe.db.set_value("VNT Business Trip Request Transportation", transport_row.name, "driver", row.driver)
				frappe.db.set_value("VNT Business Trip Request Transportation", transport_row.name, "phone", row.phone)
				frappe.db.set_value("VNT Business Trip Request Transportation", transport_row.name, "car_id", row.car_id)

		# Nếu người tạo (creator) nằm trong recipients thì loại bỏ họ
		recipients.difference_update(creator)

		driver_by_date: dict[str, list[dict[str, str]]] = {}
		driver_segments = []
		for row in self.items:
			if not row.driver:
				continue

			date_text = str(row.date) if row.date else _("(không rõ)")
			date_key = date_text

			vehicle = frappe.db.get_value(
				"VNT Vehicle",
				row.driver,
				["driver_name", "phone", "car_id"],
				as_dict=True,
			)
			driver_name = vehicle.driver_name if (vehicle and vehicle.driver_name) else row.driver
			phone = row.phone or (vehicle.phone if vehicle else "")
			car_id = row.car_id or (vehicle.car_id if vehicle else "")
			end_point = row.end or _("(không rõ)")
			start_point = row.start or _("(không rõ)")

			driver_by_date.setdefault(date_key, []).append({
				"date": date_text,
				"driver": driver_name,
				"phone": phone,
				"car_id": car_id,
				"start": start_point,
				"end": end_point,
			})

			car = registrations.get(row.id_parent)
			content = (car.note if car and car.note else None) or _("(không rõ)")

			raw_time = (row.time or "").strip()
			start_time = raw_time or _("(không rõ)")
			if raw_time and "-" in raw_time:
				parts = [p.strip() for p in raw_time.split("-") if p.strip()]
				if len(parts) >= 2:
					start_time = parts[0]
			driver_segments.append(
				"\n".join([
					_("\nNội dung:\n{0}.").format(content),
					_("Thời gian: {0} {1}.\n").format(
						start_time,
						formatdate(date_text, "dd-MM-yyyy"),
					),
					_("Lộ trình: {0} - {1}.\n").format(start_point, end_point),
					_("Phân xe: anh {0} / BKS: {1}. \n").format(
						driver_name or _("(không rõ)"),
						car_id or _("(không rõ)"),
					),
				])
			)

		# Gửi thông báo riêng cho từng dòng trong `items` (1 thông báo = 1 dòng)
		target_doctype = "VNT Car Registration"
		group_chat_target = None
		try:
			if frappe.get_meta("VNT Teams URL").has_field("group_chat_target"):
				rows = frappe.get_all("VNT Teams URL", fields=["name"], order_by="modified desc", limit=1)
				if rows:
					group_chat_target = frappe.db.get_value("VNT Teams URL", rows[0]["name"], "group_chat_target")
					group_chat_target = str(group_chat_target).strip() if group_chat_target else None
		except Exception:
			group_chat_target = None

		for row in self.items:
			if not (row.id_parent and row.id_child and row.driver):
				continue
			car = registrations.get(row.id_parent)
			if not car:
				continue
			# người nhận trong dòng này
			row_recipients = [get_employee_user_id(p.employee) for p in (car.get("list_emp") or [])]
			row_recipients = [u for u in row_recipients if u]
			row_creator = get_employee_user_id(car.get("employee"))
			# loại bỏ creator nếu nằm trong recipients
			if row_creator and row_creator in row_recipients:
				row_recipients.remove(row_creator)
			# xây dựng nội dung thông báo cho dòng
			car_item = next((item for item in (car.get("items") or []) if item.name == row.id_child), None)
			date_text = str(car_item.date) if (car_item and car_item.date) else (str(row.date) if row.date else _("(không rõ)"))
			raw_time = (row.time or "").strip()
			start_time = raw_time or _("(không rõ)")
			if raw_time and "-" in raw_time:
				parts = [p.strip() for p in raw_time.split("-") if p.strip()]
				if len(parts) >= 2:
					start_time = parts[0]
			driver_label = row.driver
			vehicle = frappe.db.get_value("VNT Vehicle", row.driver, ["driver_name", "car_id", "outside"], as_dict=True)
			if vehicle and vehicle.get("driver_name"):
				driver_label = vehicle.driver_name
			car_plate = row.car_id or (vehicle.get("car_id") if vehicle else "")

			outside_status = vehicle.get("outside") if vehicle else ""
			is_outside = (outside_status == "Thuê ngoài")
			is_out_of_car = (outside_status == "Hết xe")

			content = (car.note if car and car.note else None) or _("(không rõ)")
			if is_out_of_car:
				row_msg = "\n".join([
					_("Nội dung:\n{0}.").format(content),
					_("Thời gian: {0} {1}.").format(start_time, formatdate(date_text, "dd-MM-yyyy")),
					_("Lộ trình: {0} - {1}.").format(row.start or _("(không rõ)"), row.end or _("(không rõ)")),
				])
			elif is_outside:
				row_msg = "\n".join([
					_("Nội dung:\n{0}.").format(content),
					_("Thời gian: {0} {1}.").format(start_time, formatdate(date_text, "dd-MM-yyyy")),
					_("Lộ trình: {0} - {1}.").format(row.start or _("(không rõ)"), row.end or _("(không rõ)")),
					_("Phân xe: {0}.").format(car_plate or _("(không rõ)")),
				])
			else:
				row_msg = "\n".join([
					_("Nội dung:\n{0}.").format(content),
					_("Thời gian: {0} {1}.").format(start_time, formatdate(date_text, "dd-MM-yyyy")),
					_("Lộ trình: {0} - {1}.").format(row.start or _("(không rõ)"), row.end or _("(không rõ)")),
					_("Phân xe: anh {0} / BKS: {1}.").format(driver_label or _("(không rõ)"), car_plate or _("(không rõ)")),
				])

			# document link
			target_docname = car.name if car and car.name else self.name
			# gửi cho creator (1 người)
			if is_out_of_car:
				creator_subject = _("Văn phòng không còn xe. CBNV tự chủ động cho chuyến đi. {0}").format(row_msg)
			else:
				creator_subject = _("Bạn đã được điều xe cho chuyến đi. {0}").format(row_msg)

			if row_creator:
				make_notification_logs({
					"type": "Alert",
					"subject": creator_subject,
					"document_type": target_doctype,
					"document_name": target_docname,
				}, [row_creator])
				frappe.enqueue(
					"vinatex.integrations.teams_graph.notify_user",
					queue="default",
					timeout=50,
					is_async=True,
					upn_or_email=[row_creator],
					content_type="html",
					linkify=False,
					message=_("🔔 {0}<br>").format(creator_subject),
				)
				send_rocket_message(to_users=[row_creator], title=":bell: Thông báo", message=f"{creator_subject}.", link=get_url_to_form(target_doctype, target_docname))
			# gửi cho recipients của dòng
			if is_out_of_car:
				recipient_subject = creator_subject
			else:
				recipient_subject = _("Anh/Chị nằm trong danh sách chuyến đi. {0}").format(row_msg)

			if row_recipients:
				make_notification_logs({
					"type": "Alert",
					"subject": recipient_subject,
					"document_type": target_doctype,
					"document_name": target_docname,
				}, row_recipients)
				frappe.enqueue(
					"vinatex.integrations.teams_graph.notify_user",
					queue="default",
					timeout=60,
					is_async=True,
					upn_or_email=row_recipients,
					content_type="html",
					linkify=False,
					message=_("🔔 {0}<br>").format(recipient_subject),
				)
				send_rocket_message(to_users=row_recipients, title=":bell: Thông báo", message=f"{recipient_subject}.", link=get_url_to_form(target_doctype, target_docname))
		# Gửi thông báo tới các driver theo từng dòng items
		for row in self.items:
			if not (row.id_parent and row.id_child and row.driver):
				continue
			# lấy thông tin vehicle (nếu có)
			vehicle = frappe.db.get_value(
				"VNT Vehicle",
				row.driver,
				["driver_name", "phone", "car_id", "driver"],
				as_dict=True,
			)
			car = registrations.get(row.id_parent)
			driver_user = None
			if vehicle and vehicle.get("driver"):
				driver_user = get_employee_user_id(vehicle.get("driver"))
			# fallback: nếu row.driver chứa user/employee
			if not driver_user:
				driver_user = get_employee_user_id(row.driver)

			driver_label = (vehicle.get("driver_name") if vehicle else None) or row.driver
			car_plate = row.car_id or (vehicle.get("car_id") if vehicle else "")
			# danh sách nhân sự đi cùng cho dòng này (không liệt kê `car.employee`)
			passengers = (car.get("list_emp") if car else []) or []
			passenger_names = []
			car_employee = car.get("employee") if car else None
			for p in passengers:
				emp_name = getattr(p, "employee_name", None) if hasattr(p, "employee_name") else (p.get("employee_name") if isinstance(p, dict) else None)
				emp = getattr(p, "employee", None) if hasattr(p, "employee") else (p.get("employee") if isinstance(p, dict) else None)
				# bỏ qua nếu employee của car nằm trong list_emp
				if emp and car_employee and emp == car_employee:
					continue
				if not emp_name and emp:
					emp_name = frappe.db.get_value("Employee", emp, "employee_name")
				if emp_name:
					passenger_names.append(emp_name)
			passenger_part = _(" Nhân sự đi cùng: {0}.").format(", ".join(passenger_names)) if passenger_names else ""
			requester_text = (car.employee_name if car and getattr(car, 'employee_name', None) else _("(không rõ)"))
			if car and getattr(car, 'department', None):
				requester_text = f"{requester_text} - {car.department}"
			driver_msg = _(
				"Phân xe: Xin xe {0} của {1}. Cho anh {2} /BKS: {3}.{4} Thời gian: {5} - ngày {6}. Đón tại: {7} - điểm đến: {8}."
			).format(
				(car.note if car and getattr(car, 'note', None) else _("(không rõ)")),
				requester_text,
				driver_label,
				car_plate or _("(không rõ)"),
				passenger_part,
				row.time or _("(không rõ)"),
				formatdate(row.date, "dd-MM-yyyy") if row.date else _("(không rõ)"),
				row.start or _("(không rõ)"),
				row.end or _("(không rõ)"),
			)
			driver_msg_html = driver_msg.replace("Phân xe", "<b>Phân xe</b>", 1) if driver_msg else driver_msg
			target_docname = car.name if car and car.name else self.name
			if driver_user:
				make_notification_logs({
					"type": "Alert",
					"subject": driver_msg,
					"document_type": target_doctype,
					"document_name": target_docname,
				}, [driver_user])
				frappe.enqueue(
					"vinatex.integrations.teams_graph.notify_user",
					queue="default",
					timeout=50,
					is_async=True,
					upn_or_email=[driver_user],
					content_type="html",
					linkify=False,
					message=driver_msg
				)
			if group_chat_target:
				frappe.enqueue(
					"vinatex.integrations.teams_graph.notify_chat",
					queue="long",
					timeout=900,
					is_async=True,
					enqueue_after_commit=True,
					chat_id_or_url=group_chat_target,
					content_type="html",
					linkify=False,
					message=driver_msg_html,
				)
			# send_rocket_message(
			# 	to_users=[driver_user],
			# 	title=":bell: Thông báo",
			# 	message=driver_msg,
			# 	link=get_url_to_form(target_doctype, target_docname),
			# )
		# close todo của người điều xe cụ thể
		dispatcher_user = get_employee_user_id(self.employee)
		if dispatcher_user:
			todos = frappe.get_all(
				"ToDo",
				filters={
					"reference_type": self.doctype,
					"reference_name": self.name,
					"allocated_to": dispatcher_user,
					"status": ["not in", ["Closed", "Cancelled"]],
				},
				pluck="name",
			)
			for n in todos:
				frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


def get_employee_user_id(employee_name: str) -> str | None:
    if not employee_name:
        return None
    return frappe.db.get_value("Employee", employee_name, "user_id")


@frappe.whitelist()
def get_taken_vehicles(date, branch=None):
	if not date:
		return []

	query = """
		SELECT
			item.id_parent,
			item.driver,
			item.start,
			item.end,
			item.date,
			item.time,
			COALESCE(item.employee_name, parent.employee_name) AS employee_name
		FROM `tabVNT Vehicle Control Item` item
		INNER JOIN `tabVNT Vehicle Control` parent ON parent.name = item.parent
		LEFT JOIN `tabVNT Vehicle` v ON v.name = item.driver
		WHERE item.date = %(date)s
		  AND COALESCE(item.driver, '') != ''
	"""
	
	params = {"date": date}
	
	if branch:
		query += " AND v.branch = %(branch)s"
		params["branch"] = branch
		
	query += " ORDER BY item.time, item.start, item.end"

	return frappe.db.sql(query, params, as_dict=True)

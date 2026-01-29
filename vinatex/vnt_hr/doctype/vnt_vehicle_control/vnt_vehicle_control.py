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
					recipients.add(create_user)

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

		if not recipients:
			return

		date_text_list = sorted({formatdate(d, "dd-MM-yyyy") for d in trip_dates if d})
		date_text = ", ".join(date_text_list) if date_text_list else _("(không rõ)")

		driver_by_date: dict[str, list[str]] = {}
		for row in self.items:
			if not row.driver:
				continue
			date_key = formatdate(row.date) if row.date else _("(không rõ)")
			vehicle = frappe.db.get_value(
				"VNT Vehicle",
				row.driver,
				["driver_name", "phone", "car_id"],
				as_dict=True,
			)
			driver_name = vehicle.driver_name if (vehicle and vehicle.driver_name) else row.driver
			phone = row.phone or (vehicle.phone if vehicle else "")
			car_id = row.car_id or (vehicle.car_id if vehicle else "")
			parts = [driver_name]
			if phone:
				parts.append(phone)
			if car_id:
				parts.append(car_id)
			driver_by_date.setdefault(date_key, []).append(" - ".join(parts))

		if driver_by_date:
			driver_segments = []
			for date_key in sorted(driver_by_date.keys()):
				driver_lines = [
					_("Lái xe - {0}").format(driver_info)
					for driver_info in driver_by_date[date_key]
				]
				drivers = ";\n".join(driver_lines)
				driver_segments.append(_("Ngày {0}: {1}").format(date_key, drivers))
			driver_text = "\n".join(driver_segments)
		else:
			driver_text = _("(không rõ)")
		target_doctype = "VNT Car Registration"
		target_docname = next(
			(car.name for car in registrations.values() if car and car.name),
			self.name,
		)

		make_notification_logs({
			"type": "Alert",
			"subject": _("Bạn đã được điều xe cho chuyến đi. {0}.").format(
				# date_text,
				driver_text,
			),
			"document_type": target_doctype,
			"document_name": target_docname,
		}, list(recipients))
		frappe.enqueue(
			"vinatex.integrations.teams_graph.notify_user",
			queue="short",
			timeout=50,
			is_async=True,
			upn_or_email=list(recipients),
			content_type="html",
			linkify=False,
			message=_(
			"🔔 Bạn đã được điều xe cho chuyến đi. {0}.<br>"
			).format(
				driver_text
			),
		)
		send_rocket_message(
			to_users=list(recipients),
			title=":bell: Thông báo",
			message=_("Bạn đã được điều xe cho chuyến đi. {0}.").format(
				# date_text,
				driver_text,
			),
			link=get_url_to_form(target_doctype, target_docname)
    	)
		# Gửi thông báo tới các driver (nếu có)
		driver_sent = set()
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
			driver_user = None
			if vehicle and vehicle.get("driver"):
				driver_user = get_employee_user_id(vehicle.get("driver"))
			# fallback: nếu row.driver chứa user/employee
			if not driver_user:
				driver_user = get_employee_user_id(row.driver)
			if not driver_user:
				continue
			if driver_user in driver_sent:
				continue
			driver_sent.add(driver_user)
			driver_label = (vehicle.get("driver_name") if vehicle else None) or row.driver
			car_plate = row.car_id or (vehicle.get("car_id") if vehicle else "")
			driver_msg = _(
				"Phân xe: {0} xin xe của {1}. Cho anh {2} /BKS: {3}. Thời gian đi: {4} - ngày {5}. Đón tại: {6} - điểm đến: {7}."
			).format(
				car.department or _("(không rõ)"),
				car.employee_name or _("(không rõ)"),
				driver_label,
				car_plate or _("(không rõ)"),
				row.time or _("(không rõ)"),
				formatdate(row.date, "dd-MM-yyyy") if row.date else _("(không rõ)"),
				row.start or _("(không rõ)"),
				row.end or _("(không rõ)"),
			)
			make_notification_logs({
				"type": "Alert",
				"subject": driver_msg,
				"document_type": target_doctype,
				"document_name": target_docname,
			}, [driver_user])
			frappe.enqueue(
				"vinatex.integrations.teams_graph.notify_user",
				queue="short",
				timeout=50,
				is_async=True,
				upn_or_email=[driver_user],
				content_type="html",
				linkify=False,
				message=driver_msg
			)
			send_rocket_message(
				to_users=[driver_user],
				title=":bell: Thông báo",
				message=driver_msg,
				link=get_url_to_form(target_doctype, target_docname),
			)
		# close todo của người điều xe
		user_group_name = "Nhận thông báo điều xe"
		user_list = frappe.get_all(
			"User Group Member",
			filters={"parent": user_group_name},
			pluck="user",
		)
		names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": self.doctype,
			"reference_name": self.name,
			"allocated_to": user_list[0],
			"status": ["!=", "Cancelled"],
		},
		pluck="name",
		)
		for n in names:
			frappe.db.set_value("ToDo", n, "status", "Closed", update_modified=False)


def get_employee_user_id(employee_name: str) -> str | None:
    if not employee_name:
        return None
    return frappe.db.get_value("Employee", employee_name, "user_id")


@frappe.whitelist()
def get_taken_vehicles(date):
	if not date:
		return []

	return frappe.db.sql(
		"""
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
		WHERE item.date = %(date)s
		  AND COALESCE(item.driver, '') != ''
		ORDER BY item.time, item.start, item.end
		""",
		{"date": date},
		as_dict=True,
	)

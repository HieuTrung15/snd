# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.utils import formatdate


class VNTVehicleControl(Document):
	def on_update(self):
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
				if user:
					recipients.add(user)

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
				frappe.db.set_value(
					"VNT Business Trip Request Transportation",
					transport_row.name,
					"driver",
					row.driver,
				)

		if not recipients:
			return

		formatted_dates = sorted({formatdate(d, "dd-MM-yyyy") for d in trip_dates if d})
		date_text = ", ".join(formatted_dates) if formatted_dates else _("(không rõ)")
		target_doctype = self.doctype
		target_docname = self.name

		business_trip_name = next(
			(
				car.get("business_trip")
				for car in registrations.values()
				if car and car.get("business_trip")
			),
			None,
		)
		if business_trip_name:
			target_doctype = "VNT Business Trip Request"
			target_docname = business_trip_name

		make_notification_logs({
			"type": "Alert",
			"subject": _("Bạn đã được điều xe cho chuyến đi ngày {0}. Vui lòng xem chi tiết.").format(date_text),
			"document_type": target_doctype,
			"document_name": target_docname,
		}, list(recipients))


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
			item.time
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

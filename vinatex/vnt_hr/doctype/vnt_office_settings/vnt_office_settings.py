# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTOfficeSettings(Document):
	pass


def get_office_settings():
	try:
		return frappe.get_single("VNT Office Settings")
	except Exception:
		return None


def get_gift_handler_employee() -> str | None:
	settings = get_office_settings()
	if not settings:
		return None
	return (settings.get("gift_handler") or "").strip() or None


def get_office_manager_employee() -> str | None:
	settings = get_office_settings()
	if not settings:
		return None
	return (settings.get("office_manager") or "").strip() or None


def get_room_follower(room_name: str | None) -> tuple[str | None, str]:
	if not room_name:
		return None, ""

	follower = frappe.db.get_value(
		"VNT Office Room Follower",
		{
			"parenttype": "VNT Office Settings",
			"parent": "VNT Office Settings",
			"room_name": room_name,
		},
		"follower",
	)
	if not follower:
		return None, ""
	follower_name = frappe.db.get_value("Employee", follower, "employee_name") or ""
	return follower, follower_name


def get_approver_lv2_employee() -> str | None:
	settings = get_office_settings()
	if not settings:
		return None
	return (settings.get("approver_lv2") or "").strip() or None


@frappe.whitelist()
def get_room_follower_info(room_name: str | None = None) -> dict:
	follower, follower_name = get_room_follower(room_name)
	return {
		"follower": follower,
		"follower_name": follower_name,
	}


@frappe.whitelist()
def get_gift_handler_info() -> dict:
	follower = get_gift_handler_employee()
	if not follower:
		return {}
	follower_name = frappe.db.get_value("Employee", follower, "employee_name") or ""
	return {
		"follower": follower,
		"follower_name": follower_name,
	}


@frappe.whitelist()
def get_approver_lv2_info() -> dict:
	approver = get_approver_lv2_employee()
	if not approver:
		return {}
	approver_name = frappe.db.get_value("Employee", approver, "employee_name") or ""
	return {
		"approver_lv2": approver,
		"approver_lv2_name": approver_name,
	}

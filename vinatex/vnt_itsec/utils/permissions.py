from __future__ import annotations

import frappe

ROLES = [
    "Infomation Technology",
    "VNT External IT User"
]


def ensure_roles_and_permissions() -> None:
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert(
                ignore_permissions=True
            )

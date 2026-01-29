from __future__ import annotations

import frappe

ROLES = [
    "VNT_ITSEC_ADMIN",
    "VNT_ITSEC_ANALYST",
    "VNT_UNIT_IT_ADMIN",
    "VNT_UNIT_IT_EDITOR",
    "VNT_UNIT_VIEWER",
]


def ensure_roles_and_permissions() -> None:
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert(
                ignore_permissions=True
            )

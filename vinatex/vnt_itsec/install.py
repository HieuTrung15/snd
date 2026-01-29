from __future__ import annotations

import frappe

from vinatex.vnt_itsec.doctype_factory.create_doctypes import ensure_doctypes
from vinatex.vnt_itsec.sync.run import ensure_default_sources
from vinatex.vnt_itsec.ui import ensure_ui
from vinatex.vnt_itsec.utils.permissions import ensure_roles_and_permissions


def bootstrap(units: int = 5) -> dict:
    """Bootstrap doctypes, roles, and sources for POC (no sample companies/users)."""
    frappe.db.begin()

    ensure_roles_and_permissions()
    ensure_doctypes()
    ensure_default_sources()
    ensure_ui()

    frappe.db.commit()
    return {"ok": True, "units": units}

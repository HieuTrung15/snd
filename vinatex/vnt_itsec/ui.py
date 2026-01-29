from __future__ import annotations

import json

import frappe


WORKSPACE_NAME = "VNT IT Security"
PAGE_NAME = "itsec-dashboard"


def _workspace_shortcuts() -> list[dict]:
    return [
        {"label": "ITSEC Dashboard", "link_to": PAGE_NAME, "type": "Page"},
        {"label": "CVE Sources", "link_to": "VNT CVE Source", "type": "DocType"},
        {"label": "CVE Database", "link_to": "VNT CVE", "type": "DocType"},
        {"label": "IT Assets", "link_to": "VNT IT Asset", "type": "DocType"},
        {"label": "Asset Types", "link_to": "VNT IT Asset Type", "type": "DocType"},
        {"label": "Vendors", "link_to": "VNT IT Vendor", "type": "DocType"},
        {"label": "Products", "link_to": "VNT IT Product", "type": "DocType"},
        {"label": "Advisories", "link_to": "VNT Vulnerability Advisory", "type": "DocType"},
        {"label": "Affected Assets", "link_to": "VNT Affected Asset", "type": "DocType"},
        {"label": "Remediation Tickets", "link_to": "VNT Remediation Ticket", "type": "DocType"},
    ]


def _workspace_content() -> str:
    layout = [
        {
            "id": "itsec-header",
            "type": "header",
            "data": {"text": "<span class=\"h4\">IT Security</span>", "col": 12},
        },
        {"id": "itsec-shortcut-1", "type": "shortcut", "data": {"shortcut_name": "ITSEC Dashboard", "col": 3}},
        {"id": "itsec-shortcut-2", "type": "shortcut", "data": {"shortcut_name": "CVE Sources", "col": 3}},
        {"id": "itsec-shortcut-3", "type": "shortcut", "data": {"shortcut_name": "CVE Database", "col": 3}},
        {"id": "itsec-shortcut-4", "type": "shortcut", "data": {"shortcut_name": "IT Assets", "col": 3}},
        {"id": "itsec-shortcut-5", "type": "shortcut", "data": {"shortcut_name": "Asset Types", "col": 3}},
        {"id": "itsec-shortcut-6", "type": "shortcut", "data": {"shortcut_name": "Vendors", "col": 3}},
        {"id": "itsec-shortcut-7", "type": "shortcut", "data": {"shortcut_name": "Products", "col": 3}},
        {"id": "itsec-shortcut-8", "type": "shortcut", "data": {"shortcut_name": "Advisories", "col": 3}},
        {"id": "itsec-shortcut-9", "type": "shortcut", "data": {"shortcut_name": "Affected Assets", "col": 3}},
        {"id": "itsec-shortcut-10", "type": "shortcut", "data": {"shortcut_name": "Remediation Tickets", "col": 3}},
    ]
    return json.dumps(layout, ensure_ascii=True)


def ensure_workspace() -> None:
    if frappe.db.exists("Workspace", WORKSPACE_NAME):
        workspace = frappe.get_doc("Workspace", WORKSPACE_NAME)
        workspace.label = WORKSPACE_NAME
        workspace.title = WORKSPACE_NAME
        workspace.module = WORKSPACE_NAME
        workspace.icon = "shield"
        workspace.public = 1
        workspace.is_hidden = 0
        workspace.content = _workspace_content()
        workspace.set("shortcuts", [])
        for shortcut in _workspace_shortcuts():
            workspace.append("shortcuts", shortcut)
        workspace.save(ignore_permissions=True)
        return

    workspace = frappe.get_doc(
        {
            "doctype": "Workspace",
            "label": WORKSPACE_NAME,
            "title": WORKSPACE_NAME,
            "name": WORKSPACE_NAME,
            "module": WORKSPACE_NAME,
            "icon": "shield",
            "public": 1,
            "is_hidden": 0,
            "shortcuts": _workspace_shortcuts(),
            "content": _workspace_content(),
        }
    )
    workspace.insert(ignore_permissions=True)


def ensure_page() -> None:
    if frappe.db.exists("Page", PAGE_NAME):
        page = frappe.get_doc("Page", PAGE_NAME)
        if page.standard != "Yes":
            page.standard = "Yes"
            page.save(ignore_permissions=True)
        return

    page = frappe.get_doc(
        {
            "doctype": "Page",
            "page_name": PAGE_NAME,
            "title": "IT Security Dashboard",
            "module": WORKSPACE_NAME,
            "standard": "Yes",
            "content": "",
            "script": "",
            "style": "",
        }
    )
    page.insert(ignore_permissions=True)


def ensure_ui() -> None:
    ensure_page()
    ensure_workspace()

from __future__ import annotations

from typing import Iterable

import frappe
from frappe.utils import add_days, nowdate


def _chunked(values: list[str], size: int = 500) -> Iterable[list[str]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _delete_by_values(table: str, field: str, values: list[str]) -> int:
    if not values:
        return 0
    total = 0
    for chunk in _chunked(values):
        placeholders = ", ".join(["%s"] * len(chunk))
        frappe.db.sql(
            f"DELETE FROM `{table}` WHERE `{field}` IN ({placeholders})",
            chunk,
        )
        total += frappe.db.rowcount()
    return total


def _get_cves_to_delete(cutoff: str | None, store_only_matched: bool) -> list[str]:
    clauses = []
    params: dict[str, str] = {}

    if cutoff:
        clauses.append(
            "COALESCE(c.last_modified_date, c.published_date, c.creation) < %(cutoff)s"
        )
        params["cutoff"] = cutoff
    if store_only_matched:
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM `tabVNT Affected Asset` a WHERE a.cve = c.name)"
        )
    if not clauses:
        return []

    where_clause = " OR ".join(clauses)
    rows = frappe.db.sql(
        f"SELECT c.name FROM `tabVNT CVE` c WHERE {where_clause}",
        params,
        as_list=True,
    )
    return [row[0] for row in rows if row and row[0]]


@frappe.whitelist()
def cleanup_cves(retention_days: int | None = None, store_only_matched: int | None = None) -> dict:
    if not frappe.db.table_exists("tabVNT CVE"):
        return {"ok": True, "skipped": True, "reason": "doctype_missing"}

    cfg_retention = frappe.conf.get("vnt_itsec_cve_retention_days")
    cfg_store_only = frappe.conf.get("vnt_itsec_store_only_matched", 0)

    days = int(retention_days or cfg_retention or 0)
    only_matched = bool(store_only_matched if store_only_matched is not None else cfg_store_only)
    if only_matched and not frappe.db.table_exists("tabVNT Affected Asset"):
        only_matched = False

    cutoff = add_days(nowdate(), -days) if days > 0 else None
    to_delete = _get_cves_to_delete(cutoff=cutoff, store_only_matched=only_matched)
    if not to_delete:
        return {"ok": True, "deleted": 0, "cutoff": cutoff, "store_only_matched": only_matched}

    deleted_advisory = (
        _delete_by_values("tabVNT Advisory CVE", "cve", to_delete)
        if frappe.db.table_exists("tabVNT Advisory CVE")
        else 0
    )
    deleted_tickets = (
        _delete_by_values("tabVNT Remediation Ticket", "cve", to_delete)
        if frappe.db.table_exists("tabVNT Remediation Ticket")
        else 0
    )
    deleted_affected = (
        _delete_by_values("tabVNT Affected Asset", "cve", to_delete)
        if frappe.db.table_exists("tabVNT Affected Asset")
        else 0
    )
    deleted_cpe = (
        _delete_by_values("tabVNT CVE Affected CPE", "parent", to_delete)
        if frappe.db.table_exists("tabVNT CVE Affected CPE")
        else 0
    )
    deleted_cves = _delete_by_values("tabVNT CVE", "name", to_delete)

    frappe.db.commit()
    return {
        "ok": True,
        "deleted": deleted_cves,
        "deleted_advisory_cves": deleted_advisory,
        "deleted_tickets": deleted_tickets,
        "deleted_affected_assets": deleted_affected,
        "deleted_cpe_rows": deleted_cpe,
        "cutoff": cutoff,
        "store_only_matched": only_matched,
    }

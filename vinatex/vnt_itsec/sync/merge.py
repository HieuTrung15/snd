from __future__ import annotations

import json

import frappe


def merge_cve_records() -> None:
    """
    POC merge policy:
    - If source_primary empty, prefer CVELISTV5, then NVD, then OSV.
    """
    rows = frappe.get_all("VNT CVE", fields=["name", "source_primary", "source_ids_json"])
    for row in rows:
        if row.get("source_primary"):
            continue
        try:
            ids = json.loads(row.get("source_ids_json") or "{}")
        except Exception:
            ids = {}
        if "CVELISTV5" in ids:
            primary = "CVELISTV5"
        elif "NVD" in ids:
            primary = "NVD"
        elif "OSV" in ids:
            primary = "OSV"
        else:
            primary = "NVD"
        doc = frappe.get_doc("VNT CVE", row["name"])
        doc.source_primary = primary
        doc.save(ignore_permissions=True)

from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate


@frappe.whitelist()
def run_matching_for_advisory(advisory_name: str) -> dict:
    adv = frappe.get_doc("VNT Vulnerability Advisory", advisory_name)
    sla_days = int(adv.sla_days or 7)
    due_date = add_days(nowdate(), sla_days)

    cpe_to_cves: dict[str, list[str]] = {}
    for row in adv.cve_list:
        cve = frappe.get_doc("VNT CVE", row.cve)
        for cpe_row in (cve.affected_cpes or []):
            if not cpe_row.cpe_name:
                continue
            cpe_to_cves.setdefault(cpe_row.cpe_name, []).append(cve.name)

    if not cpe_to_cves:
        return {"ok": True, "matched": 0, "note": "No CPEs to match"}

    matched = 0
    assets = frappe.get_all("VNT IT Asset", fields=["name", "company"])
    for asset_row in assets:
        asset = frappe.get_doc("VNT IT Asset", asset_row.name)
        for comp in (asset.software_components or []):
            if not comp.cpe_name:
                continue
            cve_ids = cpe_to_cves.get(comp.cpe_name) or []
            for cve_id in cve_ids:
                component_row_id = comp.name
                base_filters = {"advisory": adv.name, "cve": cve_id, "asset": asset.name}
                exists = frappe.db.exists(
                    "VNT Affected Asset",
                    {**base_filters, "component_row_id": component_row_id},
                )
                if not exists:
                    exists = frappe.db.exists(
                        "VNT Affected Asset",
                        {**base_filters, "component_row_id": ["is", "not set"]},
                    )
                if exists:
                    continue
                frappe.get_doc(
                    {
                        "doctype": "VNT Affected Asset",
                        "advisory": adv.name,
                        "cve": cve_id,
                        "company": asset.company,
                        "asset": asset.name,
                        "component_row_id": component_row_id,
                        "match_type": "CPE",
                        "match_confidence": "High",
                        "risk_score": 10,
                        "status": "Open",
                        "due_date": due_date,
                    }
                ).insert(ignore_permissions=True)
                matched += 1

    frappe.db.commit()
    return {"ok": True, "matched": matched}

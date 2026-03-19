from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate

from vinatex.vnt_itsec.sync.common import normalize_select_key, select_value


_CRITICALITY_MULTIPLIER = {
    "Critical": 1.25,
    "High": 1.1,
    "Medium": 1.0,
    "Low": 0.9,
}

_EXPOSURE_MULTIPLIER = {
    "Internet-facing": 1.3,
    "DMZ": 1.15,
    "OT/SCADA": 1.2,
    "Internal": 1.0,
}

_SEVERITY_BASE_SCORE = {
    "Critical": 9.8,
    "High": 8.0,
    "Medium": 5.5,
    "Low": 3.2,
}


def _advisory_company_scope(adv_doc) -> set[str]:
    return {
        row.company
        for row in (adv_doc.scope_units or [])
        if getattr(row, "company", None)
    }


def _build_risk_score(cve_ctx: dict, asset_doc) -> float:
    base_score = float(cve_ctx.get("cvss_base_score") or 0)
    if base_score <= 0:
        base_score = float(_SEVERITY_BASE_SCORE.get(cve_ctx.get("severity"), 5.0))

    criticality = normalize_select_key(asset_doc.criticality) or "Medium"
    exposure = normalize_select_key(asset_doc.exposure) or "Internal"
    crit_mul = _CRITICALITY_MULTIPLIER.get(criticality, 1.0)
    exp_mul = _EXPOSURE_MULTIPLIER.get(exposure, 1.0)
    return round(min(10.0, max(0.0, base_score * crit_mul * exp_mul)), 2)


def _iter_cve_context(adv_doc) -> tuple[dict[str, list[str]], dict[str, dict]]:
    cpe_to_cves: dict[str, list[str]] = {}
    cve_context: dict[str, dict] = {}

    for row in adv_doc.cve_list:
        cve = frappe.get_doc("VNT CVE", row.cve)
        cve_context[cve.name] = {
            "severity": normalize_select_key(cve.severity) or "Unknown",
            "cvss_base_score": cve.cvss_base_score,
        }
        for cpe_row in (cve.affected_cpes or []):
            cpe = (cpe_row.cpe_name or "").strip()
            if not cpe:
                continue
            cpe_to_cves.setdefault(cpe, []).append(cve.name)

    return cpe_to_cves, cve_context


@frappe.whitelist()
def run_matching_for_advisory(advisory_name: str, commit: int = 1) -> dict:
    adv = frappe.get_doc("VNT Vulnerability Advisory", advisory_name)
    if normalize_select_key(adv.status) == "Closed":
        return {
            "ok": True,
            "matched": 0,
            "note": "Advisory is closed",
            "advisory": adv.name,
        }

    sla_days = int(adv.sla_days or 7)
    due_date = add_days(nowdate(), sla_days)

    cpe_to_cves, cve_context = _iter_cve_context(adv)

    if not cpe_to_cves:
        return {
            "ok": True,
            "matched": 0,
            "note": "No CPEs to match",
            "advisory": adv.name,
        }

    matched = 0
    asset_filters = {}
    scope_companies = _advisory_company_scope(adv)
    if scope_companies:
        asset_filters["company"] = ["in", sorted(scope_companies)]

    assets = frappe.get_all("VNT IT Asset", fields=["name", "company"], filters=asset_filters)
    scanned_assets = 0
    for asset_row in assets:
        asset = frappe.get_doc("VNT IT Asset", asset_row.name)
        scanned_assets += 1
        for comp in (asset.software_components or []):
            cpe = (comp.cpe_name or "").strip()
            if not cpe:
                continue
            cve_ids = cpe_to_cves.get(cpe) or []
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
                        "match_type": select_value("VNT Affected Asset", "match_type", "CPE"),
                        "match_confidence": select_value(
                            "VNT Affected Asset", "match_confidence", "High"
                        ),
                        "risk_score": _build_risk_score(cve_context.get(cve_id) or {}, asset),
                        "status": select_value("VNT Affected Asset", "status", "Open"),
                        "due_date": due_date,
                    }
                ).insert(ignore_permissions=True)
                matched += 1

    if int(commit):
        frappe.db.commit()
    return {"ok": True, "matched": matched, "advisory": adv.name, "scanned_assets": scanned_assets}


@frappe.whitelist()
def run_matching_for_active_advisories(commit: int = 1) -> dict:
    closed_value = select_value("VNT Vulnerability Advisory", "status", "Closed")
    advisories = frappe.get_all(
        "VNT Vulnerability Advisory",
        filters={"status": ["not in", [closed_value, "Closed"]]},
        fields=["name"],
        order_by="modified desc",
    )
    results = []
    total_matched = 0
    for row in advisories:
        result = run_matching_for_advisory(row.name, commit=0)
        results.append(result)
        total_matched += int(result.get("matched") or 0)

    if int(commit):
        frappe.db.commit()
    return {
        "ok": True,
        "advisories": len(advisories),
        "matched": total_matched,
        "results": results,
    }

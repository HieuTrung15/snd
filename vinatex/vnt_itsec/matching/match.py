from __future__ import annotations

import re

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
_VERSION_TOKEN_RE = re.compile(r"\d+|[a-z]+")


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

    criticality = normalize_select_key(
        getattr(asset_doc, "criticality", None) or (asset_doc or {}).get("criticality")
    ) or "Medium"
    exposure = normalize_select_key(
        getattr(asset_doc, "exposure", None) or (asset_doc or {}).get("exposure")
    ) or "Internal"
    crit_mul = _CRITICALITY_MULTIPLIER.get(criticality, 1.0)
    exp_mul = _EXPOSURE_MULTIPLIER.get(exposure, 1.0)
    return round(min(10.0, max(0.0, base_score * crit_mul * exp_mul)), 2)


def _split_cpe(cpe_name: str | None) -> list[str]:
    raw = (cpe_name or "").strip()
    if not raw.startswith("cpe:2.3:"):
        return []
    return raw.split(":")


def _normalize_cpe_fragment(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("\\", "")
    raw = re.sub(r"[^a-z0-9._-]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw


def _normalize_version(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("\\", "")
    if raw in {"", "*", "-"}:
        return ""
    return raw


def _tokenize_version(value: str | None) -> list[str]:
    normalized = _normalize_version(value)
    if not normalized:
        return []
    tokens = _VERSION_TOKEN_RE.findall(normalized)
    return tokens or [normalized]


def _remaining_version_effect(tokens: list[str]) -> int:
    for token in tokens:
        if token.isdigit():
            if int(token) != 0:
                return 1
            continue
        return -1
    return 0


def _compare_versions(left: str | None, right: str | None) -> int:
    left_normalized = _normalize_version(left)
    right_normalized = _normalize_version(right)
    if left_normalized == right_normalized:
        return 0

    left_tokens = _tokenize_version(left_normalized)
    right_tokens = _tokenize_version(right_normalized)
    if not left_tokens or not right_tokens:
        return (left_normalized > right_normalized) - (left_normalized < right_normalized)

    for index in range(max(len(left_tokens), len(right_tokens))):
        if index >= len(left_tokens):
            return -_remaining_version_effect(right_tokens[index:])
        if index >= len(right_tokens):
            return _remaining_version_effect(left_tokens[index:])

        left_token = left_tokens[index]
        right_token = right_tokens[index]
        if left_token == right_token:
            continue

        left_is_digit = left_token.isdigit()
        right_is_digit = right_token.isdigit()
        if left_is_digit and right_is_digit:
            return (int(left_token) > int(right_token)) - (int(left_token) < int(right_token))
        if left_is_digit != right_is_digit:
            return 1 if left_is_digit else -1
        return (left_token > right_token) - (left_token < right_token)

    return 0


def _component_context(component_row) -> dict:
    cpe_name = (component_row.cpe_name or "").strip()
    parts = _split_cpe(cpe_name)
    vendor = _normalize_cpe_fragment(parts[3] if len(parts) > 3 else component_row.vendor)
    product = _normalize_cpe_fragment(parts[4] if len(parts) > 4 else component_row.product)
    version = _normalize_version(component_row.version or (parts[5] if len(parts) > 5 else ""))
    return {
        "cpe_name": cpe_name,
        "vendor": vendor,
        "product": product,
        "version": version,
    }


def _affected_cpe_key(cpe_name: str | None) -> tuple[str, str]:
    parts = _split_cpe(cpe_name)
    if len(parts) <= 5:
        return ("", "")
    return (_normalize_cpe_fragment(parts[3]), _normalize_cpe_fragment(parts[4]))


def _version_matches(component_ctx: dict, affected_row: dict) -> bool:
    version = component_ctx.get("version") or ""
    cpe_parts = _split_cpe(affected_row.get("cpe_name"))
    affected_version = _normalize_version(cpe_parts[5] if len(cpe_parts) > 5 else "")

    start_including = _normalize_version(affected_row.get("version_start_including"))
    start_excluding = _normalize_version(affected_row.get("version_start_excluding"))
    end_including = _normalize_version(affected_row.get("version_end_including"))
    end_excluding = _normalize_version(affected_row.get("version_end_excluding"))
    has_range = any((start_including, start_excluding, end_including, end_excluding))

    if has_range:
        if not version:
            return False
        if start_including and _compare_versions(version, start_including) < 0:
            return False
        if start_excluding and _compare_versions(version, start_excluding) <= 0:
            return False
        if end_including and _compare_versions(version, end_including) > 0:
            return False
        if end_excluding and _compare_versions(version, end_excluding) >= 0:
            return False
        return True

    if not affected_version:
        return True
    if not version:
        return False
    return _compare_versions(version, affected_version) == 0


def _match_confidence(component_ctx: dict, affected_row: dict) -> str:
    if component_ctx.get("cpe_name") == (affected_row.get("cpe_name") or "").strip():
        return "High"
    has_range = any(
        _normalize_version(affected_row.get(field))
        for field in (
            "version_start_including",
            "version_start_excluding",
            "version_end_including",
            "version_end_excluding",
        )
    )
    if has_range:
        return "Medium"
    return "High"


def _matching_cves_for_component(component_ctx: dict, indexed_cpes: dict) -> list[dict]:
    key = (component_ctx.get("vendor") or "", component_ctx.get("product") or "")
    if not all(key):
        return []

    matches_by_cve: dict[str, dict] = {}
    for affected_row in indexed_cpes.get(key) or []:
        if not _version_matches(component_ctx, affected_row):
            continue
        cve_id = affected_row["cve"]
        confidence = _match_confidence(component_ctx, affected_row)
        existing = matches_by_cve.get(cve_id)
        if not existing or existing["match_confidence"] == "Medium" and confidence == "High":
            matches_by_cve[cve_id] = {"cve": cve_id, "match_confidence": confidence}
    return list(matches_by_cve.values())


def _iter_cve_context(adv_doc) -> tuple[dict[tuple[str, str], list[dict]], dict[str, dict]]:
    indexed_cpes: dict[tuple[str, str], list[dict]] = {}
    cve_context: dict[str, dict] = {}

    for row in adv_doc.cve_list:
        cve = frappe.get_doc("VNT CVE", row.cve)
        cve_context[cve.name] = {
            "severity": normalize_select_key(cve.severity) or "Unknown",
            "cvss_base_score": cve.cvss_base_score,
        }
        for cpe_row in (cve.affected_cpes or []):
            cpe_name = (cpe_row.cpe_name or "").strip()
            key = _affected_cpe_key(cpe_name)
            if not cpe_name or not all(key):
                continue
            indexed_cpes.setdefault(key, []).append(
                {
                    "cve": cve.name,
                    "cpe_name": cpe_name,
                    "version_start_including": cpe_row.version_start_including,
                    "version_start_excluding": cpe_row.version_start_excluding,
                    "version_end_including": cpe_row.version_end_including,
                    "version_end_excluding": cpe_row.version_end_excluding,
                }
            )

    return indexed_cpes, cve_context


def _affected_cpe_rows_for_component(component_ctx: dict, cache: dict) -> list[dict]:
    key = (component_ctx.get("vendor") or "", component_ctx.get("product") or "")
    if not all(key):
        return []
    if key not in cache:
        vendor, product = key
        cache[key] = frappe.db.sql(
            """
            select
                parent as cve,
                cpe_name,
                version_start_including,
                version_start_excluding,
                version_end_including,
                version_end_excluding
            from `tabVNT CVE Affected CPE`
            where ifnull(vulnerable, 1) = 1
              and cpe_name like %(pattern)s
            """,
            {"pattern": f"cpe:2.3:%:{vendor}:{product}:%"},
            as_dict=True,
        )
        cache[key] = [
            row
            for row in cache[key]
            if _affected_cpe_key(row.get("cpe_name")) == key
        ]
    return cache[key]


def _asset_rows_with_components(asset_filters: dict) -> tuple[list[dict], dict[str, list[dict]]]:
    asset_rows = frappe.get_all(
        "VNT IT Asset",
        filters=asset_filters,
        fields=["name", "company", "criticality", "exposure"],
        order_by="modified desc",
    )
    if not asset_rows:
        return [], {}

    component_rows = frappe.get_all(
        "VNT IT Software Component",
        filters={
            "parent": ["in", [row.name for row in asset_rows]],
            "parenttype": "VNT IT Asset",
        },
        fields=["name", "parent", "cpe_name", "version", "vendor", "product"],
        order_by="idx asc",
    )
    by_asset: dict[str, list[dict]] = {}
    for row in component_rows:
        by_asset.setdefault(row.parent, []).append(row)
    return asset_rows, by_asset


def find_candidate_cves_for_assets(asset_names: list[str] | None = None) -> dict[str, dict]:
    asset_filters = {"lifecycle_status": "Active"}
    if asset_names:
        asset_filters["name"] = ["in", sorted(set(asset_names))]

    asset_rows, component_map = _asset_rows_with_components(asset_filters)
    affected_cache: dict[tuple[str, str], list[dict]] = {}
    candidates: dict[str, dict] = {}

    for asset in asset_rows:
        for component in component_map.get(asset.name) or []:
            component_ctx = _component_context(component)
            if not component_ctx.get("cpe_name"):
                continue
            candidate_rows = _affected_cpe_rows_for_component(component_ctx, affected_cache)
            for affected_row in candidate_rows:
                if not _version_matches(component_ctx, affected_row):
                    continue
                cve_id = affected_row.get("cve")
                if not cve_id:
                    continue
                entry = candidates.setdefault(
                    cve_id,
                    {
                        "companies": set(),
                        "assets": set(),
                        "component_row_ids": set(),
                        "match_confidences": set(),
                    },
                )
                if asset.company:
                    entry["companies"].add(asset.company)
                entry["assets"].add(asset.name)
                if getattr(component, "name", None):
                    entry["component_row_ids"].add(component.name)
                entry["match_confidences"].add(_match_confidence(component_ctx, affected_row))

    return candidates


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

    indexed_cpes, cve_context = _iter_cve_context(adv)

    if not indexed_cpes:
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

    assets, component_map = _asset_rows_with_components(asset_filters)
    scanned_assets = 0
    for asset in assets:
        scanned_assets += 1
        for comp in component_map.get(asset.name) or []:
            component_ctx = _component_context(comp)
            if not component_ctx.get("cpe_name"):
                continue
            for match in _matching_cves_for_component(component_ctx, indexed_cpes):
                cve_id = match["cve"]
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
                            "VNT Affected Asset", "match_confidence", match["match_confidence"]
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

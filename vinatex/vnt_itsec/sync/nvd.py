from __future__ import annotations

import time
from datetime import datetime

import requests
import frappe
from frappe.utils import add_days, now_datetime

from vinatex.vnt_itsec.sync.common import (
    maybe_set_raw_json,
    normalize_severity,
    set_source_ids,
    set_source_payload,
)
from vinatex.vnt_itsec.utils.dt import parse_source_datetime


def _get_api_key() -> str:
    return frappe.conf.get("vnt_itsec_nvd_api_key") or ""


def _headers() -> dict:
    headers = {"Accept": "application/json"}
    api_key = _get_api_key()
    if api_key:
        headers["apiKey"] = api_key
    return headers


def _pick_cvss(metrics: dict) -> tuple[str, float | None, str | None, str | None]:
    version_map = {"cvssMetricV31": "3.1", "cvssMetricV30": "3.0", "cvssMetricV2": "2.0"}
    for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
        entries = metrics.get(key) or []
        if not entries:
            continue
        cvss = entries[0].get("cvssData") or {}
        base_score = cvss.get("baseScore")
        vector = cvss.get("vectorString")
        severity = normalize_severity(cvss.get("baseSeverity"))
        return severity, base_score, vector, version_map.get(key)
    return "Unknown", None, None, None


def _iter_cpe_matches(configurations: list[dict]) -> list[dict]:
    matches: list[dict] = []

    def walk_node(node: dict) -> None:
        for match in node.get("cpeMatch") or []:
            matches.append(match)
        for child in node.get("children") or []:
            walk_node(child)

    for cfg in configurations:
        for node in cfg.get("nodes") or []:
            walk_node(node)

    return matches


def _upsert_affected_cpes_from_nvd(doc, cve: dict) -> None:
    configs = cve.get("configurations") or []
    existing = {
        (
            row.cpe_name,
            row.version_start_including,
            row.version_start_excluding,
            row.version_end_including,
            row.version_end_excluding,
        )
        for row in (doc.affected_cpes or [])
        if row.cpe_name
    }
    for match in _iter_cpe_matches(configs):
        cpe = match.get("criteria")
        if not cpe:
            continue
        key = (
            cpe,
            match.get("versionStartIncluding"),
            match.get("versionStartExcluding"),
            match.get("versionEndIncluding"),
            match.get("versionEndExcluding"),
        )
        if key in existing:
            continue
        doc.append(
            "affected_cpes",
            {
                "cpe_name": cpe,
                "version_start_including": match.get("versionStartIncluding"),
                "version_start_excluding": match.get("versionStartExcluding"),
                "version_end_including": match.get("versionEndIncluding"),
                "version_end_excluding": match.get("versionEndExcluding"),
                "vulnerable": 1 if match.get("vulnerable") else 0,
            },
        )
        existing.add(key)


def _max_datetime(current: datetime | None, new_value: datetime | None) -> datetime | None:
    if not current:
        return new_value
    if not new_value:
        return current
    return max(current, new_value)


def _upsert_cve_from_nvd(item: dict) -> datetime | None:
    cve = item.get("cve", {})
    cve_id = cve.get("id")
    if not cve_id:
        return None

    published = parse_source_datetime(cve.get("published"))
    modified = parse_source_datetime(cve.get("lastModified"))

    descriptions = cve.get("descriptions") or []
    desc = ""
    for entry in descriptions:
        if entry.get("lang") == "en":
            desc = entry.get("value") or ""
            break
    if not desc and descriptions:
        desc = descriptions[0].get("value") or ""

    severity = "Unknown"
    base_score = None
    vector = None
    cvss_version = None
    metrics = cve.get("metrics") or {}
    severity, base_score, vector, cvss_version = _pick_cvss(metrics)

    if frappe.db.exists("VNT CVE", cve_id):
        doc = frappe.get_doc("VNT CVE", cve_id)
    else:
        doc = frappe.get_doc(
            {"doctype": "VNT CVE", "cve_id": cve_id, "first_seen_at": now_datetime()}
        )

    if published and (not doc.published_date or doc.source_primary in (None, "NVD")):
        doc.published_date = published

    if modified:
        current = parse_source_datetime(doc.last_modified_date)
        doc.last_modified_date = _max_datetime(current, modified)

    if desc:
        doc.description = desc

    if base_score is not None:
        doc.cvss_base_score = float(base_score)
        doc.severity = severity
    if vector:
        doc.vector_string = vector
    if cvss_version:
        doc.cvss_version = cvss_version

    references = cve.get("references") or []
    if references and (not doc.references_json or doc.source_primary in (None, "NVD")):
        doc.references_json = frappe.as_json(references)

    if not doc.source_primary:
        doc.source_primary = "NVD"

    set_source_ids(doc, "NVD", cve_id)
    set_source_payload(doc, "NVD", item)
    maybe_set_raw_json(doc, "NVD", item)

    _upsert_affected_cpes_from_nvd(doc, cve)

    doc.save(ignore_permissions=True)
    return modified


def sync_nvd_incremental(source_doc) -> dict:
    """
    Incremental sync by lastModified window with overlap.
    """
    base_url = (source_doc.api_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("NVD api_base_url is empty")

    watermark = parse_source_datetime(source_doc.watermark_source_ts)
    if not watermark:
        watermark = add_days(now_datetime(), -3)
    start = add_days(watermark, -2)
    end = now_datetime()

    def iso(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    params = {
        "lastModStartDate": iso(start),
        "lastModEndDate": iso(end),
        "resultsPerPage": 2000,
        "startIndex": 0,
    }

    total = 0
    max_modified: datetime | None = None
    while True:
        resp = requests.get(base_url, headers=_headers(), params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        vulns = data.get("vulnerabilities") or []
        for vuln in vulns:
            modified = _upsert_cve_from_nvd(vuln)
            max_modified = _max_datetime(max_modified, modified)
            total += 1
            if source_doc.max_per_run and total >= int(source_doc.max_per_run):
                break

        if source_doc.max_per_run and total >= int(source_doc.max_per_run):
            break

        start_index = params["startIndex"]
        results_per_page = params["resultsPerPage"]
        total_results = data.get("totalResults") or 0
        next_index = start_index + results_per_page
        if next_index >= total_results:
            break
        params["startIndex"] = next_index
        time.sleep(0.3)

    if max_modified:
        source_doc.watermark_source_ts = max_modified
    source_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"source": "NVD", "count": total}

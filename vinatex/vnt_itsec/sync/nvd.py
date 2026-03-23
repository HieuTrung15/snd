from __future__ import annotations

import time
from datetime import datetime

import requests
import frappe
from frappe.utils import add_days, now_datetime

from vinatex.vnt_itsec.sync.common import (
    maybe_set_raw_json,
    normalize_select_key,
    normalize_severity,
    select_value,
    set_source_ids,
    set_source_payload,
)
from vinatex.vnt_itsec.utils.dt import parse_source_datetime


def _get_api_key(source_doc=None) -> str:
    if source_doc:
        try:
            api_key = source_doc.get_password("api_key") or ""
        except Exception:
            api_key = (source_doc.api_key or "")
        if api_key:
            return api_key
    return frappe.conf.get("vnt_itsec_nvd_api_key") or ""


def _headers(source_doc=None) -> dict:
    headers = {"Accept": "application/json"}
    api_key = _get_api_key(source_doc=source_doc)
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


def _get_conf_int(key: str, default: int) -> int:
    value = frappe.conf.get(key)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _page_size() -> int:
    return max(1, min(_get_conf_int("vnt_itsec_nvd_page_size", 2000), 2000))


def _apply_nvd_payload_to_doc(doc, cve: dict, item: dict) -> datetime | None:
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

    source_primary = normalize_select_key(doc.source_primary)

    if published and (not doc.published_date or source_primary == "NVD"):
        doc.published_date = published

    if modified:
        current = parse_source_datetime(doc.last_modified_date)
        doc.last_modified_date = _max_datetime(current, modified)

    if desc:
        doc.description = desc

    if base_score is not None:
        doc.cvss_base_score = float(base_score)
        doc.severity = select_value("VNT CVE", "severity", severity)
    if vector:
        doc.vector_string = vector
    if cvss_version:
        doc.cvss_version = select_value("VNT CVE", "cvss_version", cvss_version)

    references = cve.get("references") or []
    if references and (not doc.references_json or source_primary == "NVD"):
        doc.references_json = frappe.as_json(references)

    if not doc.source_primary:
        doc.source_primary = select_value("VNT CVE", "source_primary", "NVD")

    set_source_ids(doc, "NVD", cve.get("id"))
    set_source_payload(doc, "NVD", item)
    maybe_set_raw_json(doc, "NVD", item)

    _upsert_affected_cpes_from_nvd(doc, cve)
    return modified


def _upsert_cve_from_nvd(item: dict) -> datetime | None:
    cve = item.get("cve", {})
    cve_id = cve.get("id")
    if not cve_id:
        return None

    is_existing = frappe.db.exists("VNT CVE", cve_id)
    if is_existing:
        doc = frappe.get_doc("VNT CVE", cve_id)
    else:
        doc = frappe.get_doc(
            {"doctype": "VNT CVE", "cve_id": cve_id, "first_seen_at": now_datetime()}
        )

    modified = _apply_nvd_payload_to_doc(doc, cve, item)
    try:
        doc.save(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        doc = frappe.get_doc("VNT CVE", cve_id)
        _apply_nvd_payload_to_doc(doc, cve, item)
        doc.save(ignore_permissions=True)

    return modified


def _sync_nvd_window(
    source_doc,
    start: datetime,
    end: datetime,
    *,
    limit: int | None = None,
) -> dict:
    base_url = (source_doc.api_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("NVD api_base_url is empty")

    params = {
        "lastModStartDate": _iso(start),
        "lastModEndDate": _iso(end),
        "resultsPerPage": _page_size(),
        "startIndex": 0,
    }

    total = 0
    max_modified: datetime | None = None
    total_results = 0
    hit_limit = False
    while True:
        resp = requests.get(
            base_url,
            headers=_headers(source_doc=source_doc),
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        total_results = max(total_results, int(data.get("totalResults") or 0))
        vulns = data.get("vulnerabilities") or []
        for vuln in vulns:
            modified = _upsert_cve_from_nvd(vuln)
            max_modified = _max_datetime(max_modified, modified)
            total += 1
            if limit and total >= int(limit):
                hit_limit = True
                break

        if hit_limit:
            break

        start_index = params["startIndex"]
        results_per_page = params["resultsPerPage"]
        next_index = start_index + results_per_page
        if next_index >= total_results:
            break
        params["startIndex"] = next_index
        time.sleep(0.3)

    return {
        "count": total,
        "max_modified": max_modified,
        "hit_limit": hit_limit,
        "total_results": total_results,
        "window_start": start,
        "window_end": end,
    }


def sync_nvd_incremental(source_doc) -> dict:
    """
    Incremental sync by lastModified window with overlap.
    """
    watermark = parse_source_datetime(source_doc.watermark_source_ts)
    if not watermark:
        watermark = add_days(now_datetime(), -3)
    overlap_days = max(0, _get_conf_int("vnt_itsec_nvd_incremental_overlap_days", 2))
    start = add_days(watermark, -overlap_days)
    end = now_datetime()
    limit = int(source_doc.max_per_run) if source_doc.max_per_run else None

    result = _sync_nvd_window(source_doc, start, end, limit=limit)
    if result["max_modified"]:
        source_doc.watermark_source_ts = result["max_modified"]
    source_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "source": "NVD",
        "mode": "INCREMENTAL",
        "count": result["count"],
        "window_start": _iso(result["window_start"]),
        "window_end": _iso(result["window_end"]),
        "hit_limit": result["hit_limit"],
        "total_results": result["total_results"],
    }


def backfill_nvd(source_doc) -> dict:
    """
    Backfill older NVD windows without disturbing the incremental watermark.
    """
    history_days = max(1, _get_conf_int("vnt_itsec_nvd_backfill_history_days", 730))
    window_days = max(1, _get_conf_int("vnt_itsec_nvd_backfill_window_days", 90))
    overlap_days = max(0, _get_conf_int("vnt_itsec_nvd_backfill_overlap_days", 2))
    cutoff = add_days(now_datetime(), -history_days)

    cursor = parse_source_datetime(source_doc.watermark_cursor)
    if not cursor:
        cursor = parse_source_datetime(source_doc.watermark_source_ts) or now_datetime()
    cursor = min(cursor, now_datetime())
    if cursor <= cutoff:
        return {
            "source": "NVD",
            "mode": "BACKFILL",
            "count": 0,
            "skipped": True,
            "reason": "backfill_complete",
            "cursor": _iso(cursor),
            "cutoff": _iso(cutoff),
        }

    end = cursor
    start = add_days(end, -window_days)
    if start < cutoff:
        start = cutoff

    result = _sync_nvd_window(source_doc, start, end, limit=None)

    # watermark_cursor acts as the next backfill anchor so daily incremental can keep its own watermark.
    next_cursor = add_days(start, overlap_days)
    if next_cursor >= end:
        next_cursor = start
    source_doc.watermark_cursor = _iso(next_cursor)
    source_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "source": "NVD",
        "mode": "BACKFILL",
        "count": result["count"],
        "window_start": _iso(result["window_start"]),
        "window_end": _iso(result["window_end"]),
        "cursor": source_doc.watermark_cursor,
        "cutoff": _iso(cutoff),
        "total_results": result["total_results"],
    }

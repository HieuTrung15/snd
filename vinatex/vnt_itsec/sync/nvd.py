from __future__ import annotations

import json
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


def _logger():
    return frappe.logger("vnt_itsec", allow_site=True)


def _log_info(message: str, **context) -> None:
    if context:
        message = f"{message} | {frappe.as_json(context)}"
    _logger().info(message)


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


def _load_backfill_state(source_doc) -> dict:
    raw = (source_doc.watermark_cursor or "").strip()
    state: dict = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            compact_key_map = {
                "r": "run_id",
                "c": "cursor_ts",
                "ws": "window_start",
                "we": "window_end",
                "i": "start_index",
            }
            expanded: dict = {}
            for key, value in parsed.items():
                if value in (None, "", [], {}):
                    continue
                expanded[compact_key_map.get(key, key)] = value
            state = expanded
        else:
            dt_value = parse_source_datetime(raw)
            if dt_value:
                state["cursor_ts"] = _iso(dt_value)

    if not state.get("cursor_ts"):
        cursor = parse_source_datetime(source_doc.watermark_source_ts) or now_datetime()
        state["cursor_ts"] = _iso(min(cursor, now_datetime()))
    return state


def _save_backfill_state(source_doc, state: dict) -> None:
    clean_state = {k: v for k, v in (state or {}).items() if v not in (None, "", [], {})}
    compact_key_map = {
        "run_id": "r",
        "cursor_ts": "c",
        "window_start": "ws",
        "window_end": "we",
        "start_index": "i",
    }
    compact_state = {
        compact_key_map.get(key, key): value
        for key, value in clean_state.items()
    }
    source_doc.watermark_cursor = frappe.as_json(compact_state) if compact_state else None
    source_doc.save(ignore_permissions=True)


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
    except (frappe.DuplicateEntryError, frappe.TimestampMismatchError):
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
    start_index: int = 0,
    max_pages: int | None = None,
    commit_each_page: bool = False,
    run_id: str | None = None,
) -> dict:
    base_url = (source_doc.api_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("NVD api_base_url is empty")

    _log_info(
        "NVD sync window started",
        source=getattr(source_doc, "name", "NVD"),
        window_start=_iso(start),
        window_end=_iso(end),
        limit=limit,
        start_index=start_index,
        max_pages=max_pages,
        run_id=run_id,
    )

    params = {
        "lastModStartDate": _iso(start),
        "lastModEndDate": _iso(end),
        "resultsPerPage": _page_size(),
        "startIndex": max(0, int(start_index or 0)),
    }

    total = 0
    max_modified: datetime | None = None
    total_results = 0
    hit_limit = False
    pages_processed = 0
    next_start_index = params["startIndex"]
    window_complete = False
    page_no = 0
    while True:
        page_no += 1
        try:
            resp = requests.get(
                base_url,
                headers=_headers(source_doc=source_doc),
                params=params,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            _logger().exception(
                "NVD sync request failed | %s",
                frappe.as_json(
                    {
                        "source": getattr(source_doc, "name", "NVD"),
                        "window_start": _iso(start),
                        "window_end": _iso(end),
                        "run_id": run_id,
                        "page_no": page_no,
                        "start_index": params["startIndex"],
                    }
                ),
            )
            raise
        total_results = max(total_results, int(data.get("totalResults") or 0))
        vulns = data.get("vulnerabilities") or []
        for vuln in vulns:
            modified = _upsert_cve_from_nvd(vuln)
            max_modified = _max_datetime(max_modified, modified)
            total += 1
            if limit and total >= int(limit):
                hit_limit = True
                break

        if commit_each_page:
            frappe.db.commit()
        pages_processed += 1

        _log_info(
            "NVD sync page completed",
            source=getattr(source_doc, "name", "NVD"),
            run_id=run_id,
            page_no=page_no,
            page_items=len(vulns),
            total_processed=total,
            total_results=total_results,
            pages_processed=pages_processed,
            start_index=params["startIndex"],
            hit_limit=hit_limit,
        )

        if hit_limit:
            next_start_index = params["startIndex"]
            break

        start_index = params["startIndex"]
        results_per_page = params["resultsPerPage"]
        next_index = start_index + results_per_page
        if next_index >= total_results:
            window_complete = True
            next_start_index = 0
            break
        next_start_index = next_index
        if max_pages and pages_processed >= int(max_pages):
            break
        params["startIndex"] = next_index
        time.sleep(0.3)

    result = {
        "count": total,
        "max_modified": max_modified,
        "hit_limit": hit_limit,
        "total_results": total_results,
        "window_start": start,
        "window_end": end,
        "pages_processed": pages_processed,
        "next_start_index": next_start_index,
        "window_complete": window_complete,
    }
    _log_info(
        "NVD sync window finished",
        source=getattr(source_doc, "name", "NVD"),
        run_id=run_id,
        window_start=_iso(start),
        window_end=_iso(end),
        count=total,
        total_results=total_results,
        hit_limit=hit_limit,
        max_modified=_iso(max_modified) if max_modified else None,
        pages_processed=pages_processed,
        next_start_index=next_start_index,
        window_complete=window_complete,
    )
    return result


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


def backfill_nvd(source_doc, run_id: str | None = None) -> dict:
    """
    Backfill older NVD windows without disturbing the incremental watermark.
    Each invocation processes only a few pages, then returns resumable state.
    """
    history_days = max(1, _get_conf_int("vnt_itsec_nvd_backfill_history_days", 730))
    window_days = max(1, _get_conf_int("vnt_itsec_nvd_backfill_window_days", 90))
    overlap_days = max(0, _get_conf_int("vnt_itsec_nvd_backfill_overlap_days", 2))
    max_pages = max(1, _get_conf_int("vnt_itsec_nvd_backfill_max_pages_per_job", 2))
    cutoff = add_days(now_datetime(), -history_days)
    state = _load_backfill_state(source_doc)
    run_id = run_id or state.get("run_id") or frappe.generate_hash(length=10)

    cursor = parse_source_datetime(state.get("cursor_ts")) or now_datetime()
    cursor = min(cursor, now_datetime())

    window_start = parse_source_datetime(state.get("window_start"))
    window_end = parse_source_datetime(state.get("window_end"))
    start_index = int(state.get("start_index") or 0)
    if not (window_start and window_end):
        if cursor <= cutoff:
            result = {
                "source": "NVD",
                "mode": "BACKFILL",
                "run_id": run_id,
                "count": 0,
                "skipped": True,
                "reason": "backfill_complete",
                "cursor": _iso(cursor),
                "cutoff": _iso(cutoff),
                "has_more": False,
            }
            _save_backfill_state(source_doc, {"cursor_ts": _iso(cursor)})
            _log_info("NVD backfill skipped", **result)
            return result

        window_end = cursor
        window_start = add_days(window_end, -window_days)
        if window_start < cutoff:
            window_start = cutoff
        start_index = 0

    chunk = _sync_nvd_window(
        source_doc,
        window_start,
        window_end,
        limit=None,
        start_index=start_index,
        max_pages=max_pages,
        commit_each_page=True,
        run_id=run_id,
    )

    if chunk["window_complete"]:
        next_cursor = add_days(window_start, overlap_days)
        if next_cursor >= window_end:
            next_cursor = window_start
        has_more = next_cursor > cutoff
        next_state = {"cursor_ts": _iso(next_cursor)}
        if has_more:
            next_state["run_id"] = run_id
    else:
        next_cursor = cursor
        has_more = True
        next_state = {
            "run_id": run_id,
            "window_start": _iso(window_start),
            "window_end": _iso(window_end),
            "start_index": chunk["next_start_index"],
        }

    _save_backfill_state(source_doc, next_state)
    frappe.db.commit()

    result = {
        "source": "NVD",
        "mode": "BACKFILL",
        "run_id": run_id,
        "count": chunk["count"],
        "window_start": _iso(window_start),
        "window_end": _iso(window_end),
        "cursor": _iso(next_cursor),
        "cutoff": _iso(cutoff),
        "total_results": chunk["total_results"],
        "pages_processed": chunk["pages_processed"],
        "next_start_index": chunk["next_start_index"],
        "window_complete": chunk["window_complete"],
        "has_more": has_more,
    }
    _log_info("NVD backfill chunk finished", **result)
    return result

from __future__ import annotations

import json
from datetime import datetime

import requests
import frappe
from frappe.utils import now_datetime

from vinatex.vnt_itsec.sync.common import (
    maybe_set_raw_json,
    normalize_select_key,
    select_value,
    set_source_ids,
    set_source_payload,
)
from vinatex.vnt_itsec.utils.dt import parse_source_datetime

OSV_QUERY = "https://api.osv.dev/v1/querybatch"


def _sample_packages_for_poc() -> list[dict]:
    return [
        {"package": {"name": "django", "ecosystem": "PyPI"}, "version": "3.2.0"},
        {"package": {"name": "requests", "ecosystem": "PyPI"}, "version": "2.19.0"},
        {"package": {"name": "lodash", "ecosystem": "npm"}, "version": "4.17.15"},
    ]


def _configured_queries() -> list[dict]:
    cfg = frappe.conf.get("vnt_itsec_osv_queries")
    if not cfg:
        return []
    if isinstance(cfg, list):
        return [row for row in cfg if isinstance(row, dict)]
    if isinstance(cfg, str):
        try:
            data = json.loads(cfg)
        except Exception:
            return []
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    return []


def _query_url(source_doc) -> str:
    base = (source_doc.api_base_url or "").strip().rstrip("/")
    if not base:
        return OSV_QUERY
    if base.endswith("/v1/querybatch"):
        return base
    if base.endswith("/v1"):
        return f"{base}/querybatch"
    return f"{base}/v1/querybatch"


def _extract_references(vuln: dict) -> list[dict]:
    refs = vuln.get("references") or []
    return [r for r in refs if isinstance(r, dict)]


def _upsert_from_osv(vuln: dict) -> datetime | None:
    aliases = vuln.get("aliases") or []
    cve_ids = [alias for alias in aliases if isinstance(alias, str) and alias.startswith("CVE-")]
    primary_id = cve_ids[0] if cve_ids else vuln.get("id")
    if not primary_id:
        return None

    published = parse_source_datetime(vuln.get("published"))
    modified = parse_source_datetime(vuln.get("modified"))

    if frappe.db.exists("VNT CVE", primary_id):
        doc = frappe.get_doc("VNT CVE", primary_id)
    else:
        doc = frappe.get_doc(
            {"doctype": "VNT CVE", "cve_id": primary_id, "first_seen_at": now_datetime()}
        )
    source_primary = normalize_select_key(doc.source_primary)

    if published and (not doc.published_date or source_primary == "OSV"):
        doc.published_date = published

    if modified:
        current = parse_source_datetime(doc.last_modified_date)
        if not current or modified > current:
            doc.last_modified_date = modified

    summary = vuln.get("summary") or ""
    details = vuln.get("details") or ""
    if details or summary:
        doc.description = details or summary

    references = _extract_references(vuln)
    if references and (not doc.references_json or source_primary == "OSV"):
        doc.references_json = frappe.as_json(references)

    if not doc.source_primary:
        doc.source_primary = select_value("VNT CVE", "source_primary", "OSV")

    set_source_ids(doc, "OSV", vuln.get("id"))
    set_source_payload(doc, "OSV", vuln)
    maybe_set_raw_json(doc, "OSV", vuln)

    doc.save(ignore_permissions=True)
    return modified or published


def sync_osv_batch(source_doc) -> dict:
    if not frappe.conf.get("vnt_itsec_osv_enabled", 1):
        return {"source": "OSV", "count": 0, "skipped": True}

    payload = {"queries": _configured_queries() or _sample_packages_for_poc()}

    try:
        resp = requests.post(_query_url(source_doc), json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        frappe.logger("vnt_itsec").exception("OSV querybatch failed")
        return {"source": "OSV", "skipped": True, "reason": "http_error", "error": str(exc)}
    results = data.get("results") or []

    count = 0
    max_modified: datetime | None = None
    for res in results:
        vulns = res.get("vulns") or []
        for vuln in vulns:
            modified = _upsert_from_osv(vuln)
            if modified and (not max_modified or modified > max_modified):
                max_modified = modified
            count += 1
            if source_doc.max_per_run and count >= int(source_doc.max_per_run):
                break
        if source_doc.max_per_run and count >= int(source_doc.max_per_run):
            break

    if max_modified:
        source_doc.watermark_source_ts = max_modified
    source_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"source": "OSV", "count": count}

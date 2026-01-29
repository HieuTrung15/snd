from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from vinatex.vnt_itsec.sync.cvelistv5 import sync_cvelistv5_incremental
from vinatex.vnt_itsec.sync.merge import merge_cve_records
from vinatex.vnt_itsec.sync.nvd import sync_nvd_incremental
from vinatex.vnt_itsec.sync.osv import sync_osv_batch


def _get_source(code: str):
    name = frappe.db.get_value("VNT CVE Source", {"source_code": code}, "name")
    if not name:
        return None
    return frappe.get_doc("VNT CVE Source", name)


def _run_single_source(source_code: str) -> dict:
    source = _get_source(source_code)
    if not source or not source.enabled:
        return {"source": source_code, "skipped": True}

    if source_code == "CVELISTV5":
        result = sync_cvelistv5_incremental(source)
    elif source_code == "NVD":
        result = sync_nvd_incremental(source)
    elif source_code == "OSV":
        result = sync_osv_batch(source)
    else:
        return {"source": source_code, "skipped": True}

    if result.get("skipped"):
        return result

    source.last_successful_sync_at = now_datetime()
    source.save(ignore_permissions=True)
    frappe.db.commit()
    return result


def ensure_default_sources() -> None:
    defaults = [
        {
            "source_code": "NVD",
            "enabled": 1,
            "priority": 20,
            "api_base_url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
            "auth_type": "ApiKey",
            "sync_mode": "INCREMENTAL",
            "max_per_run": 2000,
        },
        {
            "source_code": "CVELISTV5",
            "enabled": 1,
            "priority": 30,
            "api_base_url": "https://github.com/CVEProject/cvelistV5",
            "auth_type": "None",
            "sync_mode": "INCREMENTAL",
            "max_per_run": 5000,
        },
        {
            "source_code": "OSV",
            "enabled": 1,
            "priority": 10,
            "api_base_url": "https://api.osv.dev",
            "auth_type": "None",
            "sync_mode": "INCREMENTAL",
            "max_per_run": 2000,
        },
    ]
    for data in defaults:
        existing = frappe.db.get_value(
            "VNT CVE Source", {"source_code": data["source_code"]}, "name"
        )
        if existing:
            continue
        frappe.get_doc({"doctype": "VNT CVE Source", **data}).insert(
            ignore_permissions=True
        )


def run_nightly() -> dict:
    """Nightly orchestration: cvelistV5 -> NVD -> OSV -> merge."""
    ensure_default_sources()

    results = [
        _run_single_source("CVELISTV5"),
        _run_single_source("NVD"),
        _run_single_source("OSV"),
    ]

    merge_cve_records()

    frappe.db.commit()
    return {"ok": True, "results": results}


@frappe.whitelist()
def trigger_sync(source_code: str | None = None, run_now: int = 0) -> dict:
    """Queue a sync job from UI. Use run_now=1 to execute inline."""
    if source_code:
        if run_now:
            return _run_single_source(source_code)
        frappe.enqueue(
            "vinatex.vnt_itsec.sync.run._run_single_source",
            queue="long",
            job_name=f"VNT ITSEC Sync {source_code}",
            source_code=source_code,
        )
        return {"queued": True, "source": source_code}

    if run_now:
        return run_nightly()

    frappe.enqueue(
        "vinatex.vnt_itsec.sync.run.run_nightly",
        queue="long",
        job_name="VNT ITSEC Nightly Sync",
    )
    return {"queued": True, "source": "ALL"}

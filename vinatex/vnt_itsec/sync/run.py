from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from vinatex.vnt_itsec.automation import run_post_sync_automation
from vinatex.vnt_itsec.sync.common import normalize_select_key, select_value
from vinatex.vnt_itsec.sync.cvelistv5 import sync_cvelistv5_incremental
from vinatex.vnt_itsec.sync.merge import merge_cve_records
from vinatex.vnt_itsec.sync.nvd import backfill_nvd, sync_nvd_incremental
from vinatex.vnt_itsec.sync.osv import sync_osv_batch

_BACKFILL_ACTIVE_KEY = "vnt_itsec:nvd_backfill_active_run"


def _logger():
    return frappe.logger("vnt_itsec", allow_site=True)


def _log_info(message: str, **context) -> None:
    if context:
        message = f"{message} | {frappe.as_json(context)}"
    _logger().info(message)
    print(message)


def _get_conf_int(key: str, default: int) -> int:
    value = frappe.conf.get(key)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _backfill_active_key() -> str:
    return f"{frappe.local.site}:{_BACKFILL_ACTIVE_KEY}"


def _get_active_backfill_run() -> str | None:
    return frappe.cache().get_value(_backfill_active_key())


def _set_active_backfill_run(run_id: str) -> None:
    frappe.cache().set_value(
        _backfill_active_key(),
        run_id,
        expires_in_sec=max(300, _get_conf_int("vnt_itsec_nvd_backfill_lock_ttl", 21600)),
    )


def _clear_active_backfill_run(run_id: str | None = None) -> None:
    active_run_id = _get_active_backfill_run()
    if run_id and active_run_id and active_run_id != run_id:
        return
    frappe.cache().delete_value(_backfill_active_key())


def _enqueue_monthly_backfill(run_id: str, force_email: int = 0, alert_email: str | None = None) -> dict:
    frappe.enqueue(
        "vinatex.vnt_itsec.sync.run.run_monthly_backfill",
        queue="long",
        timeout=max(300, _get_conf_int("vnt_itsec_nvd_backfill_job_timeout", 1800)),
        job_name=f"VNT ITSEC Monthly Backfill {run_id}",
        run_id=run_id,
        force_email=force_email,
        alert_email=alert_email,
    )
    payload = {"queued": True, "run_id": run_id, "source": "NVD", "mode": "BACKFILL"}
    _log_info("ITSEC monthly backfill chunk queued", **payload)
    return payload


def _get_source(code: str):
    normalized = normalize_select_key(code)
    value_for_field = select_value("VNT CVE Source", "source_code", normalized)
    name = frappe.db.get_value(
        "VNT CVE Source",
        {"source_code": ["in", [normalized, value_for_field]]},
        "name",
    )
    if not name:
        return None
    return frappe.get_doc("VNT CVE Source", name)


def _run_single_source(
    source_code: str,
    mode: str | None = None,
    run_post_actions: int = 1,
    force_email: int = 0,
    alert_email: str | None = None,
) -> dict:
    normalized_code = normalize_select_key(source_code)
    normalized_mode = (mode or "INCREMENTAL").strip().upper()
    _log_info("ITSEC source sync started", source=normalized_code, mode=normalized_mode)
    source = _get_source(normalized_code)
    if not source or not source.enabled:
        return {"source": normalized_code, "mode": normalized_mode, "skipped": True}

    if normalized_code == "CVELISTV5":
        result = sync_cvelistv5_incremental(source)
    elif normalized_code == "NVD":
        if normalized_mode == "BACKFILL":
            result = backfill_nvd(source)
        else:
            result = sync_nvd_incremental(source)
    elif normalized_code == "OSV":
        result = sync_osv_batch(source)
    else:
        return {"source": normalized_code, "mode": normalized_mode, "skipped": True}

    if result.get("skipped"):
        return result

    source.last_successful_sync_at = now_datetime()
    source.save(ignore_permissions=True)
    frappe.db.commit()

    if int(run_post_actions):
        merge_cve_records()
        result["automation"] = run_post_sync_automation(
            trigger=f"sync:{normalized_code}",
            force_email=force_email,
            alert_email=alert_email,
            commit=1,
        )
    _log_info("ITSEC source sync finished", source=normalized_code, mode=normalized_mode, result=result)
    return result


def _enabled_sources_in_priority() -> list[str]:
    rows = frappe.get_all(
        "VNT CVE Source",
        filters={"enabled": 1},
        fields=["source_code", "priority"],
        order_by="priority desc, modified desc",
    )
    codes = []
    for row in rows:
        normalized = normalize_select_key(row.source_code)
        if normalized in {"CVELISTV5", "NVD", "OSV"}:
            codes.append(normalized)
    if not codes:
        return ["CVELISTV5", "NVD", "OSV"]
    return codes


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
        normalized = normalize_select_key(data["source_code"])
        value_for_field = select_value("VNT CVE Source", "source_code", normalized)
        existing = frappe.db.get_value(
            "VNT CVE Source",
            {"source_code": ["in", [normalized, value_for_field]]},
            "name",
        )
        if existing:
            continue
        payload = {
            **data,
            "source_code": value_for_field,
            "auth_type": select_value("VNT CVE Source", "auth_type", data["auth_type"]),
            "sync_mode": select_value("VNT CVE Source", "sync_mode", data["sync_mode"]),
        }
        frappe.get_doc({"doctype": "VNT CVE Source", **payload}).insert(
            ignore_permissions=True
        )


def run_nightly(force_email: int = 0, alert_email: str | None = None) -> dict:
    """Nightly orchestration: cvelistV5 -> NVD -> OSV -> merge."""
    ensure_default_sources()

    results = []
    for source_code in _enabled_sources_in_priority():
        results.append(_run_single_source(source_code, run_post_actions=0))

    merge_cve_records()
    automation = run_post_sync_automation(
        trigger="nightly",
        force_email=force_email,
        alert_email=alert_email,
        commit=0,
    )

    frappe.db.commit()
    return {"ok": True, "results": results, "automation": automation}


def run_monthly_backfill(
    force_email: int = 0,
    alert_email: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Monthly NVD backfill orchestrator. Each invocation processes one resumable chunk."""
    ensure_default_sources()
    run_id = run_id or frappe.generate_hash(length=10)
    active_run_id = _get_active_backfill_run()
    if active_run_id and active_run_id != run_id:
        payload = {
            "ok": False,
            "skipped": True,
            "reason": "backfill_already_running",
            "active_run_id": active_run_id,
            "requested_run_id": run_id,
        }
        _log_info("ITSEC monthly backfill skipped", result=payload)
        return payload

    source = _get_source("NVD")
    if not source or not source.enabled:
        payload = {"ok": False, "skipped": True, "reason": "source_disabled", "run_id": run_id}
        _log_info("ITSEC monthly backfill skipped", result=payload)
        return payload

    _set_active_backfill_run(run_id)
    _log_info("ITSEC monthly backfill started", run_id=run_id)
    try:
        result = backfill_nvd(source, run_id=run_id)
        source.last_successful_sync_at = now_datetime()
        source.save(ignore_permissions=True)
        frappe.db.commit()

        if result.get("skipped"):
            _clear_active_backfill_run(run_id)
            payload = {"ok": True, "run_id": run_id, "results": [result], "automation": None}
            _log_info("ITSEC monthly backfill finished", result=payload)
            return payload

        if result.get("has_more"):
            queue_info = _enqueue_monthly_backfill(
                run_id=run_id,
                force_email=force_email,
                alert_email=alert_email,
            )
            payload = {
                "ok": True,
                "run_id": run_id,
                "results": [result],
                "automation": None,
                "queued_next": queue_info,
            }
            _log_info("ITSEC monthly backfill chunk finished", result=payload)
            return payload

        merge_cve_records()
        automation = run_post_sync_automation(
            trigger=f"monthly_backfill:{run_id}",
            force_email=force_email,
            alert_email=alert_email,
            commit=0,
        )
        frappe.db.commit()
        _clear_active_backfill_run(run_id)
        payload = {"ok": True, "run_id": run_id, "results": [result], "automation": automation}
        _log_info("ITSEC monthly backfill finished", result=payload)
        return payload
    except Exception:
        _clear_active_backfill_run(run_id)
        _logger().exception("ITSEC monthly backfill failed | %s", frappe.as_json({"run_id": run_id}))
        raise


@frappe.whitelist()
def trigger_sync(
    source_code: str | None = None,
    mode: str | None = None,
    run_now: int = 0,
    force_email: int = 0,
    alert_email: str | None = None,
) -> dict:
    """Queue a sync job from UI. Use run_now=1 to execute inline."""
    source_code = normalize_select_key(source_code)
    normalized_mode = (mode or "INCREMENTAL").strip().upper()
    if source_code:
        if source_code == "NVD" and normalized_mode == "BACKFILL":
            if run_now:
                return run_monthly_backfill(force_email=force_email, alert_email=alert_email)
            run_id = frappe.generate_hash(length=10)
            active_run_id = _get_active_backfill_run()
            if active_run_id:
                payload = {
                    "queued": False,
                    "skipped": True,
                    "reason": "backfill_already_running",
                    "active_run_id": active_run_id,
                }
                _log_info("ITSEC monthly backfill trigger skipped", result=payload)
                return payload
            return _enqueue_monthly_backfill(
                run_id=run_id,
                force_email=force_email,
                alert_email=alert_email,
            )
        if run_now:
            return _run_single_source(
                source_code,
                mode=normalized_mode,
                run_post_actions=1,
                force_email=force_email,
                alert_email=alert_email,
            )
        frappe.enqueue(
            "vinatex.vnt_itsec.sync.run._run_single_source",
            queue="long",
            job_name=f"VNT ITSEC {normalized_mode} {source_code}",
            source_code=source_code,
            mode=normalized_mode,
            run_post_actions=1,
            force_email=force_email,
            alert_email=alert_email,
        )
        return {"queued": True, "source": source_code, "mode": normalized_mode}

    if run_now:
        if normalized_mode == "BACKFILL":
            return run_monthly_backfill(force_email=force_email, alert_email=alert_email)
        return run_nightly(force_email=force_email, alert_email=alert_email)

    method = (
        "vinatex.vnt_itsec.sync.run.run_monthly_backfill"
        if normalized_mode == "BACKFILL"
        else "vinatex.vnt_itsec.sync.run.run_nightly"
    )
    enqueue_kwargs = {
        "queue": "long",
        "job_name": (
            "VNT ITSEC Monthly Backfill"
            if normalized_mode == "BACKFILL"
            else "VNT ITSEC Nightly Sync"
        ),
        "force_email": force_email,
        "alert_email": alert_email,
    }
    if normalized_mode == "BACKFILL":
        enqueue_kwargs["timeout"] = max(300, _get_conf_int("vnt_itsec_nvd_backfill_job_timeout", 1800))
    frappe.enqueue(
        method,
        **enqueue_kwargs,
    )
    return {"queued": True, "source": "ALL", "mode": normalized_mode}

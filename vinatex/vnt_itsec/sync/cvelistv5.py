from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

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


def _parse_resume_cursor(value: str | None) -> dict | None:
    raw = (value or "").strip()
    if not raw or not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if "mode" not in data or "next_index" not in data:
        return None
    return data


def _build_resume_cursor(
    mode: str, target_rev: str, next_index: int, base_rev: str | None = None
) -> str:
    payload = {
        "mode": mode,
        "target_rev": target_rev,
        "next_index": int(next_index),
    }
    if base_rev:
        payload["base_rev"] = base_rev
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _repo_path() -> str:
    return frappe.conf.get("vnt_itsec_cvelistv5_path") or "/home/frappe/vnt_itsec_data/cvelistV5"


def _repo_ready(repo: str) -> bool:
    if not os.path.isdir(repo):
        return False
    return os.path.exists(os.path.join(repo, ".git"))


def _git(*args: str) -> str:
    repo = _repo_path()
    return subprocess.check_output(["git", "-C", repo, *args], text=True).strip()


def _safe_prev_rev(default_rev: str) -> str:
    try:
        return _git("rev-parse", "HEAD~1")
    except subprocess.CalledProcessError:
        return default_rev


def _list_changed_json_files(prev_rev: str, new_rev: str) -> list[str]:
    repo = _repo_path()
    out = subprocess.check_output(
        ["git", "-C", repo, "diff", "--name-only", prev_rev, new_rev], text=True
    )
    files = [line.strip() for line in out.splitlines() if line.strip().endswith(".json")]
    return files


def _walk_all_json_files() -> list[str]:
    repo = _repo_path()
    results: list[str] = []
    for root, _, files in os.walk(repo):
        for fname in files:
            if fname.endswith(".json"):
                rel = os.path.relpath(os.path.join(root, fname), repo)
                results.append(rel)
    return results


def _read_json(rel_path: str) -> dict | None:
    path = os.path.join(_repo_path(), rel_path)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_cve_id(record: dict) -> str | None:
    meta = record.get("cveMetadata") or {}
    return meta.get("cveId") or record.get("cveId")


def _extract_dates(record: dict) -> tuple[datetime | None, datetime | None]:
    meta = record.get("cveMetadata") or {}
    published = parse_source_datetime(meta.get("datePublished"))
    modified = parse_source_datetime(meta.get("dateUpdated") or meta.get("dateModified"))
    return published, modified


def _extract_description(record: dict) -> str:
    cna = record.get("containers", {}).get("cna", {}) if record.get("containers") else {}
    descs = cna.get("descriptions") or []
    for entry in descs:
        if entry.get("lang") == "en":
            return entry.get("value") or ""
    if descs:
        return descs[0].get("value") or ""
    return ""


def _extract_references(record: dict) -> list[dict]:
    cna = record.get("containers", {}).get("cna", {}) if record.get("containers") else {}
    return cna.get("references") or []


def _extract_affected_cpes(record: dict) -> list[str]:
    cpes: set[str] = set()
    cna = record.get("containers", {}).get("cna", {}) if record.get("containers") else {}
    affected = cna.get("affected") or []
    for entry in affected:
        for candidate in entry.get("platforms") or []:
            if isinstance(candidate, str) and candidate.startswith("cpe:2.3:"):
                cpes.add(candidate)
        for candidate in entry.get("cpes") or []:
            if isinstance(candidate, str) and candidate.startswith("cpe:2.3:"):
                cpes.add(candidate)
    return list(cpes)


def _max_datetime(current: datetime | None, new_value: datetime | None) -> datetime | None:
    if not current:
        return new_value
    if not new_value:
        return current
    return max(current, new_value)


def _upsert_cve_from_cvelist(record: dict, rel_path: str) -> datetime | None:
    cve_id = _extract_cve_id(record)
    if not cve_id:
        return None

    published, modified = _extract_dates(record)
    desc = _extract_description(record)
    references = _extract_references(record)

    if frappe.db.exists("VNT CVE", cve_id):
        doc = frappe.get_doc("VNT CVE", cve_id)
    else:
        doc = frappe.get_doc(
            {"doctype": "VNT CVE", "cve_id": cve_id, "first_seen_at": now_datetime()}
        )
    source_primary = normalize_select_key(doc.source_primary)

    if published and (not doc.published_date or source_primary == "CVELISTV5"):
        doc.published_date = published

    if modified:
        current = parse_source_datetime(doc.last_modified_date)
        doc.last_modified_date = _max_datetime(current, modified)

    if desc:
        doc.description = desc

    if references and (not doc.references_json or source_primary == "CVELISTV5"):
        doc.references_json = frappe.as_json(references)

    if not doc.source_primary:
        doc.source_primary = select_value("VNT CVE", "source_primary", "CVELISTV5")

    set_source_ids(doc, "CVELISTV5", rel_path)
    set_source_payload(doc, "CVELISTV5", record)
    maybe_set_raw_json(doc, "CVELISTV5", record)

    existing = {row.cpe_name for row in (doc.affected_cpes or []) if row.cpe_name}
    for cpe in _extract_affected_cpes(record):
        if cpe in existing:
            continue
        doc.append("affected_cpes", {"cpe_name": cpe, "vulnerable": 1})
        existing.add(cpe)

    doc.save(ignore_permissions=True)
    return modified or published


def sync_cvelistv5_incremental(source_doc) -> dict:
    """
    Incremental sync using git diff. If sync_mode=FULL and no cursor, scan all JSON.
    """
    repo = _repo_path()
    if not _repo_ready(repo):
        frappe.logger("vnt_itsec").warning(
            "cvelistV5 repo not found at %s; skipping CVELISTV5 sync", repo
        )
        return {"source": "CVELISTV5", "skipped": True, "reason": "repo_not_found", "repo": repo}

    try:
        _git("fetch", "--all", "--prune")
        _git("pull", "--ff-only")
        new_rev = _git("rev-parse", "HEAD")
    except subprocess.CalledProcessError as exc:
        frappe.logger("vnt_itsec").exception("cvelistV5 git sync failed")
        return {"source": "CVELISTV5", "skipped": True, "reason": "git_error", "error": str(exc)}

    raw_cursor = source_doc.watermark_cursor or ""
    cursor_state = _parse_resume_cursor(raw_cursor)

    mode = "DIFF"
    base_rev = ""
    target_rev = new_rev
    start_index = 0

    if cursor_state:
        mode = (cursor_state.get("mode") or "DIFF").strip().upper()
        base_rev = (cursor_state.get("base_rev") or "").strip()
        target_rev = (cursor_state.get("target_rev") or "").strip() or new_rev
        start_index = max(0, int(cursor_state.get("next_index") or 0))
    else:
        previous_cursor = raw_cursor.strip()
        if source_doc.sync_mode == "FULL" and not previous_cursor:
            mode = "FULL"
            target_rev = new_rev
        else:
            base_rev = previous_cursor or _safe_prev_rev(new_rev)

    if mode == "FULL":
        files = sorted(_walk_all_json_files())
    else:
        if not base_rev:
            base_rev = _safe_prev_rev(target_rev or new_rev)
        files = _list_changed_json_files(base_rev, target_rev)
    total_files = len(files)

    count = 0
    max_modified: datetime | None = None
    next_index = start_index
    for idx in range(start_index, total_files):
        rel = files[idx]
        data = _read_json(rel)
        if not data:
            next_index = idx + 1
            continue
        if "cveMetadata" not in data and "containers" not in data:
            next_index = idx + 1
            continue
        modified = _upsert_cve_from_cvelist(data, rel)
        max_modified = _max_datetime(max_modified, modified)
        count += 1
        next_index = idx + 1
        if source_doc.max_per_run and count >= int(source_doc.max_per_run):
            break

    partial = next_index < total_files
    if max_modified:
        source_doc.watermark_source_ts = max_modified

    if partial:
        source_doc.watermark_cursor = _build_resume_cursor(
            mode=mode,
            base_rev=base_rev if mode != "FULL" else None,
            target_rev=target_rev,
            next_index=next_index,
        )
    else:
        source_doc.watermark_cursor = target_rev if target_rev else new_rev

    source_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "source": "CVELISTV5",
        "count": count,
        "scanned_files": total_files,
        "start_index": start_index,
        "next_index": next_index,
        "partial": partial,
    }

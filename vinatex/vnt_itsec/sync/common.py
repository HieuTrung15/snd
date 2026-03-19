from __future__ import annotations

import json
from typing import Any

import frappe


def merge_json_field(existing_json: str | None, patch: dict) -> dict:
    try:
        base = json.loads(existing_json) if existing_json else {}
    except Exception:
        base = {}
    base.update(patch)
    return base


def set_source_ids(doc: Any, source_code: str, source_id: str | None) -> None:
    if not source_id:
        return
    data = merge_json_field(doc.source_ids_json, {source_code: source_id})
    doc.source_ids_json = json.dumps(data, ensure_ascii=True)


def set_source_payload(doc: Any, source_code: str, payload: dict) -> None:
    data = merge_json_field(doc.source_payloads_json, {source_code: payload})
    doc.source_payloads_json = json.dumps(data, ensure_ascii=True)


def maybe_set_raw_json(doc: Any, source_code: str, payload: dict) -> None:
    current_primary = normalize_select_key(doc.source_primary)
    if not current_primary or current_primary == normalize_select_key(source_code):
        doc.raw_json = json.dumps(payload, ensure_ascii=True)


def normalize_severity(value: str | None) -> str:
    if not value:
        return "Unknown"
    normalized = value.strip().title()
    if normalized in {"Critical", "High", "Medium", "Low"}:
        return normalized
    return "Unknown"


def normalize_select_key(value: str | None) -> str:
    raw = (value or "").strip()
    if "|" in raw:
        return raw.split("|", 1)[0].strip()
    return raw


def select_value(doctype: str, fieldname: str, value: str | None) -> str:
    normalized = normalize_select_key(value)
    if not normalized:
        return normalized
    try:
        meta = frappe.get_meta(doctype)
        df = meta.get_field(fieldname)
        options = [line.strip() for line in (df.options or "").splitlines() if line.strip()]
    except Exception:
        options = []

    if normalized in options:
        return normalized
    for option in options:
        if normalize_select_key(option) == normalized:
            return option
    return normalized


def select_values(doctype: str, fieldname: str, values: list[str] | tuple[str, ...]) -> list[str]:
    resolved: list[str] = []
    for value in values:
        normalized = normalize_select_key(value)
        mapped = select_value(doctype, fieldname, value)
        for candidate in (mapped, normalized):
            if candidate and candidate not in resolved:
                resolved.append(candidate)
    return resolved

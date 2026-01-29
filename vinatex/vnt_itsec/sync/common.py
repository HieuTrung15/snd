from __future__ import annotations

import json
from typing import Any


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
    if not doc.source_primary or doc.source_primary == source_code:
        doc.raw_json = json.dumps(payload, ensure_ascii=True)


def normalize_severity(value: str | None) -> str:
    if not value:
        return "Unknown"
    normalized = value.strip().title()
    if normalized in {"Critical", "High", "Medium", "Low"}:
        return normalized
    return "Unknown"

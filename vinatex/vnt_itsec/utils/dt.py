from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from frappe.utils import get_datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_source_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt_value = value
    else:
        try:
            dt_value = get_datetime(value)
        except Exception:
            return None
    if dt_value and dt_value.tzinfo:
        return dt_value.astimezone(timezone.utc).replace(tzinfo=None)
    return dt_value

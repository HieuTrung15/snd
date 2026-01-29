from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate


def _doctype_exists(name: str) -> bool:
    return bool(frappe.db.exists("DocType", name))


def _count(doctype: str, filters: dict | list | None = None) -> int:
    if not _doctype_exists(doctype):
        return 0
    return int(frappe.db.count(doctype, filters=filters or {}))


def _date_range(days: int) -> list:
    start = getdate(add_days(nowdate(), -(days - 1)))
    return [start + timedelta(days=i) for i in range(days)]


def _format_date(value) -> str:
    try:
        return getdate(value).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _cve_trend(days: int) -> list[dict]:
    if not _doctype_exists("VNT CVE"):
        return []
    since = add_days(now_datetime(), -days)
    rows = frappe.db.sql(
        """
        select
            date(published_date) as day,
            count(*) as total,
            sum(case when severity in ('Critical','High') then 1 else 0 end) as critical_high
        from `tabVNT CVE`
        where published_date is not null and published_date >= %s
        group by date(published_date)
        """,
        (since,),
        as_dict=True,
    )
    data_map = {str(row["day"]): row for row in rows}
    series = []
    for day in _date_range(days):
        key = day.strftime("%Y-%m-%d")
        row = data_map.get(key) or {}
        series.append(
            {
                "date": key,
                "total": int(row.get("total") or 0),
                "critical_high": int(row.get("critical_high") or 0),
            }
        )
    return series


def _value_breakdown(doctype: str, field: str, values: list[str]) -> list[dict]:
    if not _doctype_exists(doctype):
        return []
    return [{"label": val, "value": _count(doctype, filters={field: val})} for val in values]


@frappe.whitelist()
def get_dashboard_data(days: int = 7, limit: int = 10) -> dict:
    days = max(1, cint(days) or 7)
    limit = max(1, cint(limit) or 10)
    since = add_days(now_datetime(), -days)
    today = nowdate()

    overview = {
        "cve_total": _count("VNT CVE"),
        "cve_new": _count("VNT CVE", filters=[["published_date", ">=", since]]),
        "critical_high": _count("VNT CVE", filters={"severity": ["in", ["Critical", "High"]]}),
        "assets_total": _count("VNT IT Asset"),
        "advisories_open": _count(
            "VNT Vulnerability Advisory", filters={"status": ["!=", "Closed"]}
        ),
        "affected_open": _count(
            "VNT Affected Asset", filters={"status": ["in", ["Open", "In Progress"]]}
        ),
        "tickets_open": _count(
            "VNT Remediation Ticket",
            filters={"status": ["not in", ["Done", "Rejected"]]},
        ),
        "tickets_overdue": _count(
            "VNT Remediation Ticket",
            filters=[
                ["status", "not in", ["Done", "Rejected"]],
                ["sla_due_date", "<", today],
            ],
        ),
    }

    severity = []
    for label in ["Critical", "High", "Medium", "Low", "Unknown"]:
        severity.append(
            {"label": label, "value": _count("VNT CVE", filters={"severity": label})}
        )

    recent = []
    if _doctype_exists("VNT CVE"):
        recent = frappe.get_all(
            "VNT CVE",
            fields=["cve_id", "severity", "published_date", "description"],
            order_by="published_date desc",
            limit=limit,
        )

    sources = []
    if _doctype_exists("VNT CVE Source"):
        sources = frappe.get_all(
            "VNT CVE Source",
            fields=[
                "name",
                "source_code",
                "enabled",
                "last_successful_sync_at",
                "watermark_source_ts",
                "sync_mode",
            ],
            order_by="priority desc",
        )

    exposure_breakdown = _value_breakdown(
        "VNT IT Asset", "exposure", ["Internal", "DMZ", "Internet-facing", "OT/SCADA"]
    )
    affected_breakdown = _value_breakdown(
        "VNT Affected Asset",
        "status",
        ["Open", "In Progress", "Mitigated", "Patched", "Not Applicable", "Accepted Risk"],
    )
    ticket_breakdown = _value_breakdown(
        "VNT Remediation Ticket",
        "status",
        ["Open", "Assigned", "In Progress", "Waiting", "Done", "Rejected"],
    )

    return {
        "overview": overview,
        "severity": severity,
        "recent": recent,
        "sources": sources,
        "cve_trend": _cve_trend(days),
        "exposure_breakdown": exposure_breakdown,
        "affected_breakdown": affected_breakdown,
        "ticket_breakdown": ticket_breakdown,
    }

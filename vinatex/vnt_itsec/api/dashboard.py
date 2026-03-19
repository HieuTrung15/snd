from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, nowdate

from vinatex.vnt_itsec.sync.common import select_values


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
    critical_high = select_values("VNT CVE", "severity", ["Critical", "High"])
    placeholders = ", ".join(["%s"] * len(critical_high))
    rows = frappe.db.sql(
        f"""
        select
            date(published_date) as day,
            count(*) as total,
            sum(case when severity in ({placeholders}) then 1 else 0 end) as critical_high
        from `tabVNT CVE`
        where published_date is not null and published_date >= %s
        group by date(published_date)
        """,
        (*critical_high, since),
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


def _value_breakdown(doctype: str, field: str, values: list[str], filters=None) -> list[dict]:
    if not _doctype_exists(doctype):
        return []
    base_filters = filters or {}
    return [
        {
            "label": val,
            "value": _count(
                doctype, filters={**base_filters, field: ["in", select_values(doctype, field, [val])]}
            ),
        }
        for val in values
    ]


@frappe.whitelist()
def get_dashboard_data(days: int = 7, limit: int = 10, company: str | None = None) -> dict:
    days = max(1, cint(days) or 7)
    limit = max(1, cint(limit) or 10)
    since = add_days(now_datetime(), -days)
    today = nowdate()
    company_filter = {"company": company} if company else None
    cve_critical_high = select_values("VNT CVE", "severity", ["Critical", "High"])
    advisory_closed = select_values("VNT Vulnerability Advisory", "status", ["Closed"])
    affected_open = select_values("VNT Affected Asset", "status", ["Open", "In Progress"])
    ticket_closed = select_values("VNT Remediation Ticket", "status", ["Done", "Rejected"])

    overview = {
        "cve_total": _count("VNT CVE"),
        "cve_new": _count("VNT CVE", filters=[["published_date", ">=", since]]),
        "critical_high": _count("VNT CVE", filters={"severity": ["in", cve_critical_high]}),
        "assets_total": _count("VNT IT Asset", filters=company_filter),
        "advisories_open": _count(
            "VNT Vulnerability Advisory", filters={"status": ["not in", advisory_closed]}
        ),
        "affected_open": _count(
            "VNT Affected Asset",
            filters={
                **(company_filter or {}),
                "status": ["in", affected_open],
            },
        ),
        "tickets_open": _count(
            "VNT Remediation Ticket",
            filters={**(company_filter or {}), "status": ["not in", ticket_closed]},
        ),
        "tickets_overdue": _count(
            "VNT Remediation Ticket",
            filters=[
                *(company_filter.items() if company_filter else []),
                ["status", "not in", ticket_closed],
                ["sla_due_date", "<", today],
            ],
        ),
    }

    severity = []
    for label in ["Critical", "High", "Medium", "Low", "Unknown"]:
        severity.append(
            {
                "label": label,
                "value": _count(
                    "VNT CVE",
                    filters={"severity": ["in", select_values("VNT CVE", "severity", [label])]},
                ),
            }
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
        "VNT IT Asset",
        "exposure",
        ["Internal", "DMZ", "Internet-facing", "OT/SCADA"],
        filters=company_filter,
    )
    affected_breakdown = _value_breakdown(
        "VNT Affected Asset",
        "status",
        ["Open", "In Progress", "Mitigated", "Patched", "Not Applicable", "Accepted Risk"],
        filters=company_filter,
    )
    ticket_breakdown = _value_breakdown(
        "VNT Remediation Ticket",
        "status",
        ["Open", "Assigned", "In Progress", "Waiting", "Done", "Rejected"],
        filters=company_filter,
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


@frappe.whitelist()
def get_dashboard_grafana(days: int = 7, limit: int = 10, company: str | None = None) -> dict:
    payload = get_dashboard_data(days=days, limit=limit, company=company)
    trend = payload.get("cve_trend") or []
    series = []
    if trend:
        series = [
            _to_series("Total CVEs", [row.get("total") for row in trend], trend),
            _to_series(
                "Critical + High", [row.get("critical_high") for row in trend], trend
            ),
        ]

    return {
        "meta": {
            "company": company,
            "days": days,
        },
        "overview": payload.get("overview") or {},
        "severity": payload.get("severity") or [],
        "exposure_breakdown": payload.get("exposure_breakdown") or [],
        "affected_breakdown": payload.get("affected_breakdown") or [],
        "ticket_breakdown": payload.get("ticket_breakdown") or [],
        "sources": payload.get("sources") or [],
        "recent": payload.get("recent") or [],
        "cve_trend": trend,
        "series": series,
    }


@frappe.whitelist()
def get_grafana_companies():
    return frappe.get_all("Company", pluck="name")


def _to_series(name: str, values: list, trend: list[dict]) -> dict:
    datapoints = []
    for value, row in zip(values, trend):
        ts = _to_ts(row.get("date"))
        datapoints.append([int(value or 0), ts])
    return {"target": name, "datapoints": datapoints}


def _to_ts(value) -> int:
    try:
        return int(get_datetime(value).timestamp() * 1000)
    except Exception:
        return 0

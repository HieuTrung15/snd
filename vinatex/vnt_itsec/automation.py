from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, now_datetime, nowdate

from vinatex.vnt_itsec.matching.match import (
    find_candidate_cves_for_assets,
    run_matching_for_active_advisories,
    run_matching_for_advisory,
)
from vinatex.vnt_itsec.sync.common import normalize_select_key, select_value, select_values

DEFAULT_ALERT_EMAIL = "sonph@vinatex.com.vn"
_OPEN_AFFECTED_STATUS_KEYS = ("Open", "In Progress")
_OPEN_TICKET_EXCLUDED_KEYS = ("Done", "Rejected")
_AUTO_ADVISORY_TITLE_PREFIX = "[AUTO]"
_SEVERITY_PRIORITY = {
    "Critical": 1,
    "High": 2,
    "Medium": 3,
    "Low": 4,
    "Unknown": 4,
}


def _to_priority_label(priority_value: int) -> str:
    level = max(1, min(4, int(priority_value or 4)))
    return f"P{level}"


def _pick_priority(cve_severity: str | None, asset_doc: dict | None) -> str:
    severity = normalize_select_key(cve_severity) or "Unknown"
    priority = int(_SEVERITY_PRIORITY.get(severity, 4))
    criticality = normalize_select_key((asset_doc or {}).get("criticality")) or ""
    exposure = normalize_select_key((asset_doc or {}).get("exposure")) or ""

    if criticality in {"Critical", "High"}:
        priority -= 1
    if exposure in {"Internet-facing", "DMZ"}:
        priority -= 1

    return _to_priority_label(priority)


def _resolve_assignee(asset_doc: dict | None, advisory_doc: dict | None) -> str:
    assignee = ((asset_doc or {}).get("service_owner") or "").strip()
    if assignee and frappe.db.exists("User", assignee):
        return assignee

    advisory_owner = ((advisory_doc or {}).get("owner") or "").strip()
    if advisory_owner and frappe.db.exists("User", advisory_owner):
        return advisory_owner

    return "Administrator"


def _resolve_due_date(affected_row: dict, advisory_doc: dict | None) -> str:
    if affected_row.get("due_date"):
        return affected_row["due_date"]

    sla_days = int((advisory_doc or {}).get("sla_days") or 7)
    return add_days(nowdate(), sla_days)


def _ticket_exists_for_affected(affected_row: dict) -> bool:
    excluded_statuses = select_values(
        "VNT Remediation Ticket", "status", _OPEN_TICKET_EXCLUDED_KEYS
    )
    return bool(
        frappe.db.exists(
            "VNT Remediation Ticket",
            {
                "advisory": affected_row.get("advisory"),
                "cve": affected_row.get("cve"),
                "asset": affected_row.get("asset"),
                "status": ["not in", excluded_statuses],
            },
        )
    )


def _create_ticket_for_affected(
    affected_row: dict, *, cve_doc: dict | None, asset_doc: dict | None, advisory_doc: dict | None
) -> str:
    ticket = frappe.get_doc(
        {
            "doctype": "VNT Remediation Ticket",
            "naming_series": select_value(
                "VNT Remediation Ticket", "naming_series", "RMD-.YYYY.-.MM.-.####"
            ),
            "company": affected_row.get("company") or (asset_doc or {}).get("company"),
            "advisory": affected_row.get("advisory"),
            "cve": affected_row.get("cve"),
            "asset": affected_row.get("asset"),
            "priority": _pick_priority((cve_doc or {}).get("severity"), asset_doc),
            "status": select_value("VNT Remediation Ticket", "status", "Open"),
            "assignee": _resolve_assignee(asset_doc, advisory_doc),
            "sla_due_date": _resolve_due_date(affected_row, advisory_doc),
            "action_plan": (
                "Auto-created from matched affected asset. "
                "Please triage, assign remediation steps, and update status."
            ),
        }
    ).insert(ignore_permissions=True)
    return ticket.name


def _asset_filters_for_candidates(asset_names: list[str] | None = None) -> dict:
    filters = {"lifecycle_status": "Active"}
    if asset_names:
        filters["name"] = ["in", sorted(set(asset_names))]
    return filters


def _asset_inventory_candidates(asset_names: list[str] | None = None) -> dict[str, dict]:
    return find_candidate_cves_for_assets(asset_names=asset_names)


def _open_advisories_for_cve(cve_id: str) -> list[dict]:
    closed_value = select_value("VNT Vulnerability Advisory", "status", "Closed")
    advisory_rows = frappe.get_all(
        "VNT Advisory CVE",
        filters={"cve": cve_id},
        fields=["parent"],
    )
    advisory_names = [row.parent for row in advisory_rows if getattr(row, "parent", None)]
    if not advisory_names:
        return []

    advisories = frappe.get_all(
        "VNT Vulnerability Advisory",
        filters={
            "name": ["in", sorted(set(advisory_names))],
            "status": ["not in", [closed_value, "Closed"]],
        },
        fields=["name", "title", "status", "severity", "sla_days"],
        order_by="modified desc",
    )
    for advisory in advisories:
        scope_rows = frappe.get_all(
            "VNT Advisory Scope Unit",
            filters={"parent": advisory.name, "parenttype": "VNT Vulnerability Advisory"},
            fields=["company"],
        )
        advisory["scope_companies"] = {
            row.company for row in scope_rows if getattr(row, "company", None)
        }
    return advisories


def _covers_companies(advisory: dict, companies: set[str]) -> bool:
    scope_companies = advisory.get("scope_companies") or set()
    if not scope_companies:
        return True
    return companies.issubset(scope_companies)


def _is_auto_advisory(advisory: dict | None) -> bool:
    title = ((advisory or {}).get("title") or "").strip()
    return title.startswith(f"{_AUTO_ADVISORY_TITLE_PREFIX} ")


def _append_scope_companies(advisory_name: str, companies: set[str]) -> bool:
    if not companies:
        return False
    advisory = frappe.get_doc("VNT Vulnerability Advisory", advisory_name)
    existing = _advisory_company_scope(advisory)
    changed = False
    for company in sorted(companies):
        if not company or company in existing:
            continue
        advisory.append("scope_units", {"company": company})
        changed = True
    if changed:
        advisory.save(ignore_permissions=True)
    return changed


def _build_auto_advisory_payload(cve_id: str, companies: set[str]) -> dict:
    cve_doc = frappe.get_value(
        "VNT CVE",
        cve_id,
        ["severity", "description", "published_date", "cisa_kev"],
        as_dict=True,
    ) or {}
    description = (cve_doc.get("description") or "").strip()
    advisory = {
        "doctype": "VNT Vulnerability Advisory",
        "naming_series": "ADV-.YYYY.-.MM.-.####",
        "title": f"{_AUTO_ADVISORY_TITLE_PREFIX} {cve_id} detected from asset inventory",
        "advisory_type": select_value("VNT Vulnerability Advisory", "advisory_type", "Awareness"),
        "status": select_value("VNT Vulnerability Advisory", "status", "Draft"),
        "severity": select_value(
            "VNT Vulnerability Advisory",
            "severity",
            normalize_select_key(cve_doc.get("severity")) or "Medium",
        ),
        "sla_days": 7,
        "description": (
            "Auto-generated from VNT IT Asset inventory because at least one active asset "
            f"matched {cve_id} by CPE.\n\n{description[:1200]}"
        ).strip(),
        "guidance": (
            "System-generated advisory. Review scope, affected assets, and remediation guidance "
            "before publishing to operations teams."
        ),
        "publish_at": cve_doc.get("published_date") or now_datetime(),
        "cve_list": [{"cve": cve_id, "note": "Auto-linked from nightly/asset automation"}],
        "scope_units": [{"company": company} for company in sorted(companies) if company],
    }
    if cve_doc.get("cisa_kev"):
        advisory["guidance"] += "\nKEV flagged: prioritize validation and remediation."
    return advisory


def ensure_candidate_advisories_from_assets(
    asset_names: list[str] | None = None,
    commit: int = 1,
) -> dict:
    candidates = _asset_inventory_candidates(asset_names=asset_names)
    created = 0
    updated = 0
    reused = 0
    advisory_names: list[str] = []
    details: list[dict] = []

    for cve_id, candidate in candidates.items():
        companies = set(candidate.get("companies") or set())
        advisories = _open_advisories_for_cve(cve_id)
        advisory_name = ""
        action = "skipped"

        for advisory in advisories:
            if _covers_companies(advisory, companies):
                advisory_name = advisory["name"]
                action = "reused"
                reused += 1
                break

        if not advisory_name:
            auto_advisory = next((row for row in advisories if _is_auto_advisory(row)), None)
            if auto_advisory:
                missing_companies = companies - (auto_advisory.get("scope_companies") or set())
                if _append_scope_companies(auto_advisory["name"], missing_companies):
                    updated += 1
                    action = "updated"
                else:
                    reused += 1
                    action = "reused"
                advisory_name = auto_advisory["name"]

        if not advisory_name:
            advisory_doc = frappe.get_doc(
                _build_auto_advisory_payload(cve_id, companies)
            ).insert(ignore_permissions=True)
            advisory_name = advisory_doc.name
            created += 1
            action = "created"

        if advisory_name:
            advisory_names.append(advisory_name)
            details.append(
                {
                    "cve": cve_id,
                    "advisory": advisory_name,
                    "companies": sorted(companies),
                    "assets": sorted(candidate.get("assets") or set()),
                    "action": action,
                }
            )

    if cint(commit):
        frappe.db.commit()

    return {
        "ok": True,
        "candidates": len(candidates),
        "created": created,
        "updated": updated,
        "reused": reused,
        "advisories": sorted(set(advisory_names)),
        "details": details,
    }


def ensure_remediation_ticket_for_affected_asset(affected_name: str, commit: int = 1) -> dict:
    if not affected_name:
        return {"ok": False, "created": 0, "skipped": 1, "reason": "missing_affected_name"}

    if not frappe.db.exists("VNT Affected Asset", affected_name):
        return {"ok": False, "created": 0, "skipped": 1, "reason": "affected_not_found"}

    row = frappe.get_value(
        "VNT Affected Asset",
        affected_name,
        ["name", "advisory", "cve", "asset", "company", "due_date", "status"],
        as_dict=True,
    )
    if not row or normalize_select_key(row.get("status")) not in _OPEN_AFFECTED_STATUS_KEYS:
        return {"ok": True, "created": 0, "skipped": 1, "reason": "affected_not_open"}
    if _ticket_exists_for_affected(row):
        return {"ok": True, "created": 0, "skipped": 1, "reason": "ticket_exists"}

    cve_doc = frappe.get_value("VNT CVE", row.cve, ["severity", "cvss_base_score"], as_dict=True)
    asset_doc = frappe.get_value(
        "VNT IT Asset",
        row.asset,
        ["company", "service_owner", "criticality", "exposure", "asset_name"],
        as_dict=True,
    )
    advisory_doc = frappe.get_value(
        "VNT Vulnerability Advisory", row.advisory, ["owner", "sla_days"], as_dict=True
    )

    ticket_name = _create_ticket_for_affected(
        row, cve_doc=cve_doc, asset_doc=asset_doc, advisory_doc=advisory_doc
    )
    if cint(commit):
        frappe.db.commit()
    return {"ok": True, "created": 1, "skipped": 0, "ticket": ticket_name, "affected": affected_name}


def ensure_remediation_tickets_for_open_affected(
    commit: int = 1,
    advisory_names: list[str] | None = None,
    asset_names: list[str] | None = None,
) -> dict:
    open_statuses = select_values("VNT Affected Asset", "status", _OPEN_AFFECTED_STATUS_KEYS)
    filters = {"status": ["in", open_statuses]}
    if advisory_names:
        filters["advisory"] = ["in", sorted(set(advisory_names))]
    if asset_names:
        filters["asset"] = ["in", sorted(set(asset_names))]
    rows = frappe.get_all(
        "VNT Affected Asset",
        filters=filters,
        fields=["name", "advisory", "cve", "asset", "company", "due_date", "status"],
        order_by="modified desc",
    )
    advisory_cache: dict[str, dict] = {}
    cve_cache: dict[str, dict] = {}
    asset_cache: dict[str, dict] = {}

    created = 0
    skipped = 0
    ticket_names: list[str] = []

    for row in rows:
        if _ticket_exists_for_affected(row):
            skipped += 1
            continue

        advisory_name = row.get("advisory")
        cve_name = row.get("cve")
        asset_name = row.get("asset")

        if advisory_name not in advisory_cache:
            advisory_cache[advisory_name] = frappe.get_value(
                "VNT Vulnerability Advisory", advisory_name, ["owner", "sla_days"], as_dict=True
            ) or {}
        if cve_name not in cve_cache:
            cve_cache[cve_name] = frappe.get_value(
                "VNT CVE", cve_name, ["severity", "cvss_base_score"], as_dict=True
            ) or {}
        if asset_name not in asset_cache:
            asset_cache[asset_name] = frappe.get_value(
                "VNT IT Asset",
                asset_name,
                ["company", "service_owner", "criticality", "exposure", "asset_name"],
                as_dict=True,
            ) or {}

        ticket_name = _create_ticket_for_affected(
            row,
            cve_doc=cve_cache[cve_name],
            asset_doc=asset_cache[asset_name],
            advisory_doc=advisory_cache[advisory_name],
        )
        ticket_names.append(ticket_name)
        created += 1

    if cint(commit):
        frappe.db.commit()

    return {
        "ok": True,
        "open_affected": len(rows),
        "created_tickets": created,
        "skipped_existing": skipped,
        "ticket_names": ticket_names,
    }


def _resolve_alert_email(explicit_email: str | None = None) -> str:
    return (
        (explicit_email or "").strip()
        or (frappe.conf.get("vnt_itsec_alert_email") or "").strip()
        or DEFAULT_ALERT_EMAIL
    )


def _send_summary_email(summary: dict, trigger: str, alert_email: str | None = None) -> dict:
    recipient = _resolve_alert_email(alert_email)
    subject = f"[VNT ITSEC] Automation Summary ({trigger})"
    matching = summary.get("matching") or {}
    tickets = summary.get("tickets") or {}
    message = (
        f"<p>Automation completed at <b>{now_datetime()}</b>.</p>"
        f"<p><b>Trigger:</b> {frappe.utils.escape_html(trigger)}</p>"
        "<ul>"
        f"<li>Matched records: <b>{int(matching.get('matched') or 0)}</b></li>"
        f"<li>Advisories processed: <b>{int(matching.get('advisories') or 0)}</b></li>"
        f"<li>Open affected assets: <b>{int(tickets.get('open_affected') or 0)}</b></li>"
        f"<li>New remediation tickets: <b>{int(tickets.get('created_tickets') or 0)}</b></li>"
        "</ul>"
    )

    ticket_names = tickets.get("ticket_names") or []
    if ticket_names:
        lines = "".join(f"<li>{frappe.utils.escape_html(name)}</li>" for name in ticket_names[:20])
        message += f"<p><b>New tickets:</b></p><ol>{lines}</ol>"

    try:
        frappe.sendmail(
            recipients=[recipient],
            subject=subject,
            message=message,
            delayed=False,
        )
        return {"ok": True, "recipient": recipient}
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "VNT ITSEC automation email failed")
        return {"ok": False, "recipient": recipient, "error": str(exc)}


@frappe.whitelist()
def run_post_sync_automation(
    trigger: str = "manual",
    force_email: int = 0,
    alert_email: str | None = None,
    commit: int = 1,
) -> dict:
    advisory_candidates = ensure_candidate_advisories_from_assets(commit=0)
    matching = run_matching_for_active_advisories(commit=0)
    tickets = ensure_remediation_tickets_for_open_affected(commit=0)

    if cint(commit):
        frappe.db.commit()

    summary = {
        "ok": True,
        "trigger": trigger,
        "candidate_advisories": advisory_candidates,
        "matching": matching,
        "tickets": tickets,
    }
    should_send_email = bool(int(force_email) or int(tickets.get("created_tickets") or 0) > 0)
    if should_send_email:
        summary["email"] = _send_summary_email(summary, trigger=trigger, alert_email=alert_email)
    else:
        summary["email"] = {"ok": True, "skipped": True}
    return summary


@frappe.whitelist()
def run_asset_inventory_automation(asset_name: str, force_email: int = 0) -> dict:
    if not asset_name:
        return {"ok": False, "reason": "missing_asset_name"}
    if not frappe.db.exists("VNT IT Asset", asset_name):
        return {"ok": False, "reason": "asset_not_found", "asset": asset_name}

    advisory_candidates = ensure_candidate_advisories_from_assets(
        asset_names=[asset_name],
        commit=0,
    )
    advisory_names = advisory_candidates.get("advisories") or []
    matching_results = []
    total_matched = 0
    for advisory_name in advisory_names:
        result = run_matching_for_advisory(advisory_name, commit=0)
        matching_results.append(result)
        total_matched += int(result.get("matched") or 0)

    tickets = ensure_remediation_tickets_for_open_affected(
        commit=0,
        advisory_names=advisory_names,
        asset_names=[asset_name],
    )
    frappe.db.commit()

    summary = {
        "ok": True,
        "trigger": f"asset:{asset_name}",
        "asset": asset_name,
        "candidate_advisories": advisory_candidates,
        "matching": {
            "advisories": len(advisory_names),
            "matched": total_matched,
            "results": matching_results,
        },
        "tickets": tickets,
    }
    if cint(force_email):
        summary["email"] = _send_summary_email(summary, trigger=f"asset:{asset_name}")
    else:
        summary["email"] = {"ok": True, "skipped": True}
    return summary


@frappe.whitelist()
def send_test_alert_email(recipient: str | None = None) -> dict:
    payload = {
        "ok": True,
        "matching": {"advisories": 0, "matched": 0},
        "tickets": {"open_affected": 0, "created_tickets": 0, "ticket_names": []},
    }
    return _send_summary_email(payload, trigger="test", alert_email=recipient)

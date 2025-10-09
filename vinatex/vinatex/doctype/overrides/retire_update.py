# retire_update.py
import frappe
from vinatex.vinatex.doctype.overrides.employee import get_retirement_date

def recalc_retirement_dates():
    logger = frappe.logger("retirement_scheduler")
    logger.info("Start recalc_retirement_dates")

    employees = frappe.get_all("Employee", fields=["name", "date_of_birth", "gender"])
    updated = 0
    skipped = 0

    for emp in employees:
        dob = emp.get("date_of_birth")
        gender = emp.get("gender")
        if not dob or not gender:
            skipped += 1
            continue
        try:
            rd = get_retirement_date(dob, gender)  # 'YYYY-MM-DD'
            frappe.db.set_value(
                "Employee", emp["name"], "date_of_retirement", rd, update_modified=False
            )
            updated += 1
        except Exception:
            logger.exception(f"Failed for Employee {emp['name']}")
            skipped += 1

    frappe.db.commit()
    msg = f"Done. Updated={updated}, Skipped={skipped}, Total={len(employees)}"
    logger.info(msg)
    return msg 
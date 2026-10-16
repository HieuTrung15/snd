from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, getdate, today
from hrms.hr.doctype.attendance.attendance import Attendance

from vinatex.vnt_hr.attendance_processing import process_attendance


class VntAttendance(Attendance):
	pass


@frappe.whitelist()
def create_attendance_from_checkin(from_date=None, to_date=None, dry_run=0):
	"""Create Attendance from the resolved shift plan and Employee Checkins.

	The scheduled run processes the month containing yesterday. An explicit date
	range is accepted for controlled backfills, while ``dry_run=1`` performs the
	full calculation without writing Shift Assignment, Checkin, or Attendance.
	"""
	dry_run = bool(cint(dry_run))
	frappe.only_for(
		("HR User", "HR Manager", "System Manager")
		if dry_run
		else ("HR Manager", "System Manager")
	)
	to_date = getdate(to_date or add_days(today(), -1))
	from_date = getdate(from_date or to_date.replace(day=1))
	return process_attendance(from_date, to_date, dry_run=dry_run)

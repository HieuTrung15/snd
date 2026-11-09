"""Controlled repairs for attendance-confirmation records."""

import frappe
from frappe.utils import cint


def delete_empty_confirmations(dry_run=True) -> dict:
	"""Delete non-cancelled confirmation parents that have no detail rows."""
	dry_run = bool(cint(dry_run))
	names = sorted(
		frappe.db.sql(
			"""
			SELECT parent.name
			FROM `tabVNT Attendance Confirm` parent
			LEFT JOIN `tabVNT Attendance Confirm Item` item
				ON item.parent = parent.name
			WHERE parent.docstatus < 2
			GROUP BY parent.name
			HAVING COUNT(item.name) = 0
			ORDER BY parent.name
			""",
			pluck=True,
		)
	)

	deleted = 0
	skipped_changed = []
	if not dry_run:
		for name in names:
			try:
				doc = frappe.get_doc(
					"VNT Attendance Confirm", name, for_update=True
				)
			except frappe.DoesNotExistError:
				skipped_changed.append(name)
				continue
			if cint(doc.docstatus) >= 2 or (doc.get("items") or []):
				skipped_changed.append(name)
				continue
			frappe.delete_doc(
				"VNT Attendance Confirm",
				name,
				ignore_permissions=True,
			)
			deleted += 1

	return {
		"Phiếu rỗng": names,
		"Số phiếu rỗng": len(names),
		"Số phiếu đã xóa": deleted,
		"Phiếu bỏ qua do đã thay đổi": skipped_changed,
		"Chạy thử": dry_run,
	}

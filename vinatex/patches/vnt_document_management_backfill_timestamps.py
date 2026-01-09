import frappe


def _safe_update(sql, params=None):
	try:
		frappe.db.sql(sql, params or {})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "VNT Document Management backfill timestamps")


def execute():
	parent_table = "tabVNT Document Management"
	child_table = "tabVNT Document Management Item"

	if frappe.db.table_exists(parent_table):
		if frappe.db.has_column(parent_table, "handler_transferred_at"):
			_safe_update(
				f"""
				UPDATE `{parent_table}`
				SET handler_transferred_at = modified
				WHERE handler_transferred_at IS NULL
				  AND (
					handler_status = 'Chuyển văn bản'
					OR IFNULL(is_handler_status, 0) = 1
				  )
				"""
			)

		if frappe.db.has_column(parent_table, "chairperson_completed_at"):
			_safe_update(
				f"""
				UPDATE `{parent_table}`
				SET chairperson_completed_at = modified
				WHERE chairperson_completed_at IS NULL
				  AND chairperson_status = 'Hoàn thành'
				"""
			)

		if frappe.db.has_column(parent_table, "cv_xu_ly_completed_at"):
			_safe_update(
				f"""
				UPDATE `{parent_table}`
				SET cv_xu_ly_completed_at = modified
				WHERE cv_xu_ly_completed_at IS NULL
				  AND trang_thai_chuyen_vien_xu_ly = 'Hoàn thành'
				"""
			)

		if frappe.db.has_column(parent_table, "cv_xu_ly_assigned_at"):
			_safe_update(
				f"""
				UPDATE `{parent_table}`
				SET cv_xu_ly_assigned_at = modified
				WHERE cv_xu_ly_assigned_at IS NULL
				  AND IFNULL(cv_xu_ly, '') != ''
				"""
			)

	if frappe.db.table_exists(child_table):
		if frappe.db.has_column(child_table, "nguoi_phoi_hop_completed_at"):
			_safe_update(
				f"""
				UPDATE `{child_table}`
				SET nguoi_phoi_hop_completed_at = modified
				WHERE nguoi_phoi_hop_completed_at IS NULL
				  AND trang_thai_nguoi_phoi_hop = 'Hoàn thành'
				"""
			)

		if frappe.db.has_column(child_table, "cv_xu_ly_completed_at"):
			_safe_update(
				f"""
				UPDATE `{child_table}`
				SET cv_xu_ly_completed_at = modified
				WHERE cv_xu_ly_completed_at IS NULL
				  AND trang_thai_cv_xu_ly = 'Hoàn thành'
				"""
			)

		if frappe.db.has_column(child_table, "cv_xu_ly_assigned_at"):
			_safe_update(
				f"""
				UPDATE `{child_table}`
				SET cv_xu_ly_assigned_at = modified
				WHERE cv_xu_ly_assigned_at IS NULL
				  AND IFNULL(cv_xu_ly, '') != ''
				"""
			)

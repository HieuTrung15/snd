import frappe
from frappe import _
from frappe.utils import flt

RATING_ROLE = "HR Headhunters"
MATCHED_STATUS = "Phù hợp"
MAX_RATING = 5
SPECIAL_RATING_MANAGER_USERS = {
	"thuhuyen@vinatex.com.vn",
	"thangnd@vinatex.com.vn",
}


def _user_has_role(user: str, role: str) -> bool:
	return role in set(frappe.get_roles(user))


def validate_job_applicant_rating(doc, method=None):
	# Fallback an toàn khi field table chưa migrate.
	if not doc.meta.get_field("custom_headhunter_ratings"):
		_validate_direct_rating_edit(doc)
		return

	_enforce_manual_edit_permissions(doc)
	_sync_headhunter_rows(doc)
	_recalculate_final_rating(doc)


def _validate_direct_rating_edit(doc):
	if doc.is_new() or not doc.has_value_changed("applicant_rating"):
		return

	if _is_privileged_user():
		return

	if not _user_has_role(frappe.session.user, RATING_ROLE):
		frappe.throw(
			_("Only users with role {0} can edit Applicant Rating.")
			.format(frappe.bold(RATING_ROLE))
		)

	if doc.status != MATCHED_STATUS:
		frappe.throw(
			_("Applicant Rating can only be updated when status is {0}.")
			.format(frappe.bold(MATCHED_STATUS))
		)


def _is_privileged_user():
	if frappe.session.user == "Administrator":
		return True
	if frappe.session.user in SPECIAL_RATING_MANAGER_USERS:
		return True
	return "System Manager" in frappe.get_roles(frappe.session.user)


def _get_rating_map(doc):
	result = {}
	for row in doc.get("custom_headhunter_ratings") or []:
		headhunter = (row.headhunter or "").strip()
		if not headhunter or headhunter in result:
			continue
		result[headhunter] = flt(row.applicant_rating)
	return result


def _enforce_manual_edit_permissions(doc):
	if doc.is_new() or _is_privileged_user():
		return

	if doc.has_value_changed("applicant_rating"):
		frappe.throw(
			_(
				"Applicant Rating cuối được tính tự động từ bảng Đánh giá Headhunter. "
				"Vui lòng không sửa trực tiếp ô Applicant Rating phía trên."
			)
		)

	old_doc = None
	if hasattr(doc, "get_doc_before_save"):
		old_doc = doc.get_doc_before_save()
	if not old_doc and not doc.is_new():
		old_doc = frappe.get_doc(doc.doctype, doc.name)
	old_doc = old_doc or doc
	old_map = _get_rating_map(old_doc)
	new_map = _get_rating_map(doc)
	changed_users = {
		user
		for user in (set(old_map) | set(new_map))
		if flt(old_map.get(user)) != flt(new_map.get(user))
	}
	if not changed_users:
		return

	if not _user_has_role(frappe.session.user, RATING_ROLE):
		frappe.throw(
			_("Only users with role {0} can update rating rows.")
			.format(frappe.bold(RATING_ROLE))
		)

	current_user = frappe.session.user
	invalid_targets = [user for user in changed_users if user != current_user]
	if invalid_targets:
		frappe.throw(_("Bạn chỉ được sửa dòng đánh giá của chính mình."))

	if doc.status != MATCHED_STATUS:
		frappe.throw(
			_("Bạn chỉ được đánh giá khi trạng thái ứng viên là {0}.")
			.format(frappe.bold(MATCHED_STATUS))
		)


def _get_headhunter_users():
	rows = frappe.db.sql(
		"""
		SELECT
			u.name AS user_id,
			COALESCE(
				MAX(CASE WHEN IFNULL(e.status, '') = 'Active' AND IFNULL(e.employee_name, '') != '' THEN e.employee_name END),
				MAX(NULLIF(e.employee_name, '')),
				NULLIF(u.full_name, ''),
				u.name
			) AS display_name
		FROM `tabHas Role` hr
		INNER JOIN `tabUser` u
			ON u.name = hr.parent
		LEFT JOIN `tabEmployee` e
			ON e.user_id = u.name
			AND e.docstatus < 2
		WHERE hr.parenttype = 'User'
		  AND hr.role = %s
		  AND IFNULL(u.enabled, 0) = 1
		  AND u.name NOT IN ('Guest')
		GROUP BY u.name, u.full_name
		ORDER BY COALESCE(NULLIF(u.full_name, ''), u.name)
		""",
		(RATING_ROLE,),
		as_dict=True,
	)
	return rows


def _get_user_display_map(user_ids):
	user_ids = tuple({(user or "").strip() for user in (user_ids or []) if (user or "").strip()})
	if not user_ids:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT
			u.name AS user_id,
			COALESCE(
				MAX(CASE WHEN IFNULL(e.status, '') = 'Active' AND IFNULL(e.employee_name, '') != '' THEN e.employee_name END),
				MAX(NULLIF(e.employee_name, '')),
				NULLIF(u.full_name, ''),
				u.name
			) AS display_name
		FROM `tabUser` u
		LEFT JOIN `tabEmployee` e
			ON e.user_id = u.name
			AND e.docstatus < 2
		WHERE u.name IN %(user_ids)s
		GROUP BY u.name, u.full_name
		""",
		{"user_ids": user_ids},
		as_dict=True,
	)
	return {(row.user_id or "").strip(): (row.display_name or row.user_id) for row in rows}


def _sync_headhunter_rows(doc):
	headhunters = _get_headhunter_users()
	headhunter_set = {row.user_id for row in headhunters}
	rating_map = {}
	manual_user_ids = []
	child_meta = frappe.get_meta("VNT Applicant Headhunter Rating")
	has_display_field = bool(child_meta.get_field("headhunter_full_name"))

	for row in doc.get("custom_headhunter_ratings") or []:
		user_id = (row.headhunter or "").strip()
		if not user_id or user_id in rating_map:
			continue
		rating_map[user_id] = min(MAX_RATING, max(0, flt(row.applicant_rating)))
		if user_id not in headhunter_set:
			manual_user_ids.append(user_id)

	if manual_user_ids:
		display_map = _get_user_display_map(manual_user_ids)
		for user_id in manual_user_ids:
			headhunters.append(
				frappe._dict(
					user_id=user_id,
					display_name=display_map.get(user_id, user_id),
				)
			)

	doc.set("custom_headhunter_ratings", [])
	for row in headhunters:
		user_id = row.user_id
		payload = {
			"headhunter": user_id,
			"applicant_rating": rating_map.get(user_id, 0),
		}
		if has_display_field:
			payload["headhunter_full_name"] = row.display_name
		doc.append(
			"custom_headhunter_ratings",
			payload,
		)


def _recalculate_final_rating(doc):
	if doc.status != MATCHED_STATUS:
		doc.applicant_rating = 0
		return

	ratings = [
		min(MAX_RATING, max(0, flt(row.applicant_rating)))
		for row in (doc.get("custom_headhunter_ratings") or [])
		if flt(row.applicant_rating) > 0
	]

	doc.applicant_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0

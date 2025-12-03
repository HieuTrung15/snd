# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.utils import getdate, nowdate, get_url_to_form
from frappe.model.document import Document
from vinatex.patches.utils.rocket_chat import send_rocket_message


class VNTDocumentManagement(Document):
	def after_insert(self):
		if (self.type or "").strip() != "Công văn đến":
			return

		self._notify_incoming_to_handler()
		self._notify_office_group()

	def _notify_incoming_to_handler(self):
		"""Gửi notification + tạo ToDo cho Lãnh đạo Tập đoàn khi nhận công văn đến lần đầu."""
		if not self.handler:
			return

		user_id = frappe.db.get_value("Employee", self.handler, "user_id")
		if not user_id:
			return

		content = f"{self.sender or ''} v/v {self.summary or ''}".strip(" /")
		if not content:
			content = "Văn bản mới"

		# Notification Log
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user_id,
				"subject": content,
				"type": "Alert",
				"document_type": self.doctype,
				"document_name": self.name,
			}
		).insert(ignore_permissions=True)

		# ToDo (tránh nhân đôi nếu đã có)
		if not frappe.db.exists(
			"ToDo",
			{
				"reference_type": self.doctype,
				"reference_name": self.name,
				"allocated_to": user_id,
				"status": ("!=", "Cancelled"),
			},
		):
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"status": "Open",
					"allocated_to": user_id,
					"reference_type": self.doctype,
					"reference_name": self.name,
					"description": content,
					"priority": "Medium",
				}
			).insert(ignore_permissions=True)

		# Rocket.Chat
		send_rocket_message(
			to_users=user_id,
			title=":bell: Thông báo Công văn đến",
			message=content,
			link=get_url_to_form(self.doctype, self.name),
		)

	def _notify_office_group(self):
		"""Gửi thông báo tới User Group 'Chánh VP nhận thông báo CV đến'."""
		group_name = "Chánh VP nhận thông báo CV đến"
		user_list = frappe.get_all(
			"User Group Member",
			filters={"parent": group_name},
			pluck="user",
		)
		if not user_list:
			return

		ref = self.reference_number or self.name
		handler_name = frappe.db.get_value("Employee", self.handler, "employee_name") if self.handler else None
		sender = self.sender or "(Không rõ nơi gửi)"
		message = f"CV đến số {ref} từ {sender} đã được chuyển cho {handler_name or '(Chưa rõ lãnh đạo xử lý)'}"

		for user in user_list:
			# Notification Log
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"subject": message,
					"type": "Alert",
					"document_type": self.doctype,
					"document_name": self.name,
				}
			).insert(ignore_permissions=True)

			# ToDo (mỗi user một ToDo, tránh trùng)
			if not frappe.db.exists(
				"ToDo",
				{
					"reference_type": self.doctype,
					"reference_name": self.name,
					"allocated_to": user,
					"status": ("!=", "Cancelled"),
				},
			):
				frappe.get_doc(
					{
						"doctype": "ToDo",
						"status": "Open",
						"allocated_to": user,
						"reference_type": self.doctype,
						"reference_name": self.name,
						"description": message,
						"priority": "Medium",
					}
				).insert(ignore_permissions=True)

		# Rocket.Chat
		send_rocket_message(
			to_users=user_list,
			title=":bell: Thông báo Công văn đến",
			message=message,
			link=get_url_to_form(self.doctype, self.name),
		)


@frappe.whitelist()
def get_level1_approvers():
	"""
	Return employees who are marked as level-1 approvers in Department.leave_approvers.
	Uses Department Approver.custom_level_1 to filter.
	"""
	# Fetch approver (user) entries that are flagged as level 1
	approver_rows = frappe.get_all(
		"Department Approver",
		filters={"parenttype": "Department", "custom_level_1": 1},
		fields=["approver"],
		distinct=True,
	)
	user_ids = {row.approver for row in approver_rows if row.approver}
	if not user_ids:
		return []

	# Map approver user_ids to Employee records
	employees = frappe.get_all(
		"Employee",
		filters={"user_id": ["in", list(user_ids)]},
		fields=["name", "employee_name", "department", "user_id"],
		distinct=True,
	)

	# Fallback: in case approver stores Employee name instead of User ID
	remaining_ids = user_ids - {emp.user_id for emp in employees if emp.user_id}
	if remaining_ids:
		extra = frappe.get_all(
			"Employee",
			filters={"name": ["in", list(remaining_ids)]},
			fields=["name", "employee_name", "department", "user_id"],
			distinct=True,
		)
		employees.extend(extra)

	seen = set()
	result = []
	for emp in employees:
		if emp.name in seen:
			continue
		seen.add(emp.name)
		result.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
			}
		)
	return result


@frappe.whitelist()
def filter_cv_xu_ly_by_collab(doctype, txt, searchfield, start, page_len, filters):
	"""
	Trả về nhân viên cùng phòng/ban với người phối hợp (nguoi_phoi_hop) trong bảng items2.
	"""
	collab = (filters or {}).get("nguoi_phoi_hop")
	if not collab:
		return []

	department = frappe.db.get_value("Employee", collab, "department")
	if not department:
		return []

	like_txt = f"%{txt or ''}%"
	rows = frappe.db.sql(
		"""
		SELECT name, employee_name
		FROM `tabEmployee`
		WHERE department = %(department)s
			AND (name LIKE %(txt)s OR employee_name LIKE %(txt)s)
		ORDER BY employee_name ASC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"department": department,
			"txt": like_txt,
			"page_len": page_len,
			"start": start,
		},
	)
	return rows



@frappe.whitelist()
def get_document_overview():
	"""
	Tổng hợp nhanh 4 nhóm việc cần theo dõi cho Custom HTML Block "Quản lý văn bản":
	- assigned: Việc đã được giao cho tôi (còn đang mở)
	- pending_assignment: Văn bản tôi là Lãnh đạo nhưng chưa giao Người chủ trì
	- completed: Việc tôi đã hoàn thành
	- overdue: Việc của tôi đã quá hạn (chưa hoàn thành)
	"""
	user = frappe.session.user
	emp = frappe.db.get_value(
		"Employee", {"user_id": user}, ["name", "employee_name"], as_dict=True
	)
	if not emp:
		return {
			"employee": None,
			"counts": {"assigned": 0, "pending_assignment": 0, "completed": 0, "overdue": 0},
			"lists": {"assigned": [], "pending_assignment": [], "completed": [], "overdue": []},
			"message": "Không tìm thấy Employee gắn với user hiện tại",
		}

	today = getdate(nowdate())
	emp_name = emp.name

	# === Thu thập các văn bản liên quan tới nhân viên hiện tại ===
	doc_names = set()

	# Lãnh đạo (handler)
	handler_docs = frappe.get_all(
		"VNT Document Management",
		filters={"handler": emp_name, "docstatus": ["<", 2]},
		fields=["name", "reference_number", "summary", "nguoi_chu_tri"],
	)
	doc_names.update(doc.name for doc in handler_docs)

	# Người chủ trì
	doc_names.update(
		row.name
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"nguoi_chu_tri": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
		)
	)

	# Chuyên viên xử lý chính
	doc_names.update(
		row.name
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"cv_xu_ly": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
		)
	)

	# Người phối hợp / chuyên viên phối hợp (từ child table)
	collab_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "nguoi_phoi_hop": emp_name},
		fields=["parent", "deadline1", "trang_thai_nguoi_phoi_hop"],
	)
	collab_spec_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "cv_xu_ly": emp_name},
		fields=["parent", "deadline2", "trang_thai_cv_xu_ly"],
	)
	doc_names.update(row.parent for row in collab_rows)
	doc_names.update(row.parent for row in collab_spec_rows)

	if not doc_names:
		return {
			"employee": emp,
			"counts": {"assigned": 0, "pending_assignment": 0, "completed": 0, "overdue": 0},
			"lists": {"assigned": [], "pending_assignment": [], "completed": [], "overdue": []},
		}

	# Lấy thông tin chi tiết văn bản để render UI
	doc_fields = [
		"name",
		"reference_number",
		"summary",
		"type",
		"handler",
		"handler_status",
		"deadline",
		"nguoi_chu_tri",
		"chairperson_status",
		"deadline_chu_tri2",
		"cv_xu_ly",
		"trang_thai_chuyen_vien_xu_ly",
		"deadline_cv_xu_ly",
		"modified",
	]
	docs = {
		row.name: row
		for row in frappe.get_all(
			"VNT Document Management", filters={"name": ["in", list(doc_names)]}, fields=doc_fields
		)
	}

	# Map child rows theo parent
	collab_by_parent = {}
	for row in collab_rows:
		collab_by_parent.setdefault(row.parent, []).append(row)

	collab_spec_by_parent = {}
	for row in collab_spec_rows:
		collab_spec_by_parent.setdefault(row.parent, []).append(row)

	def _to_date(val):
		try:
			return getdate(val) if val else None
		except Exception:
			return None

	def _is_completed(status):
		return (status or "").strip().lower() == "hoàn thành"

	assignments = []

	def _add_assignment(docname, role, status=None, deadline=None):
		doc = docs.get(docname)
		if not doc:
			return
		deadline_date = _to_date(deadline)
		is_done = _is_completed(status)
		is_overdue = bool(deadline_date and (deadline_date < today) and not is_done)
		assignments.append(
			{
				"docname": docname,
				"reference_number": doc.reference_number,
				"summary": doc.summary,
				"type": doc.type,
				"role": role,
				"status": status or "",
				"deadline": deadline_date.isoformat() if deadline_date else None,
				"overdue": is_overdue,
			}
		)

	for name, doc in docs.items():
		if doc.nguoi_chu_tri == emp_name:
			_add_assignment(name, "Người chủ trì", doc.chairperson_status, doc.deadline_chu_tri2)
		if doc.cv_xu_ly == emp_name:
			_add_assignment(name, "Chuyên viên xử lý", doc.trang_thai_chuyen_vien_xu_ly, doc.deadline_cv_xu_ly)

	for row in collab_by_parent.values():
		for item in row:
			_add_assignment(item.parent, "Người phối hợp", item.trang_thai_nguoi_phoi_hop, item.deadline1)

	for row in collab_spec_by_parent.values():
		for item in row:
			_add_assignment(item.parent, "Chuyên viên phối hợp", item.trang_thai_cv_xu_ly, item.deadline2)

	assigned_list = [a for a in assignments if not _is_completed(a.get("status"))]
	completed_list = [a for a in assignments if _is_completed(a.get("status"))]
	overdue_list = [a for a in assignments if a.get("overdue")]

	# Văn bản chưa giao Người chủ trì (dành cho lãnh đạo)
	handler_doc_names = {doc.name for doc in handler_docs}
	has_chair = set()
	if handler_doc_names:
		has_chair = {
			row.parent
			for row in frappe.get_all(
				"VNT Document Management Item2",
				filters={"parent": ["in", list(handler_doc_names)], "chu_tri": 1},
				fields=["parent"],
				distinct=True,
			)
		}
	pending_assignment = []
	for doc in handler_docs:
		if doc.nguoi_chu_tri or doc.name in has_chair:
			continue
		full_doc = docs.get(doc.name)
		pending_assignment.append(
			{
				"docname": doc.name,
				"reference_number": doc.reference_number,
				"summary": full_doc.summary if full_doc else doc.summary,
			}
		)

	# Giới hạn danh sách trả về để block render nhanh (phần tử đầu)
	def _top(lst):
		return lst[:6]

	return {
		"employee": emp,
		"counts": {
			"assigned": len(assigned_list),
			"pending_assignment": len(pending_assignment),
			"completed": len(completed_list),
			"overdue": len(overdue_list),
		},
		"lists": {
			"assigned": _top(assigned_list),
			"pending_assignment": _top(pending_assignment),
			"completed": _top(completed_list),
			"overdue": _top(overdue_list),
		},
	}

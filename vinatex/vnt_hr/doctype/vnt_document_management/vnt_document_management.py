# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.utils import getdate, nowdate, get_url_to_form
from frappe.model.document import Document
from vinatex.patches.utils.rocket_chat import send_rocket_message


class VNTDocumentManagement(Document):
	def validate(self):
		self._validate_handler_status_roles()
		self._validate_collab_vs_specialist_status()
		self._validate_chair_vs_specialist_status()
		self._validate_specialist_deadline()
		self._validate_items2_deadlines()

	def before_save(self):
		self._maybe_notify_child_assignees_on_transfer()
		self._maybe_notify_primary_specialist_assignment()
		self._maybe_notify_chair_on_specialist_done()

	def after_insert(self):
		if (self.type or "").strip() != "Công văn đến":
			return

		self._notify_incoming_to_handler()
		self._notify_office_group()

	def _validate_handler_status_roles(self):
		"""Yêu cầu phải có ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết khi đặt trạng thái lãnh đạo."""
		if not self.handler_status:
			return

		rows = self.get("items") or []
		picked = [row for row in rows if (row.chu_tri or row.phoi_hop or row.nhan_de_biet)]
		if not picked:
			frappe.throw("Vui lòng chọn ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết trước khi cập nhật Trạng thái Lãnh đạo Tập Đoàn.")

		if (self.handler_status or "").strip() == "Chuyển văn bản":
			for row in picked:
				if not row.deadline:
					frappe.throw("Dòng đã chọn vai trò chưa có Thời hạn hoàn thành. Vui lòng nhập trước khi cập nhật Trạng thái Lãnh đạo Tập Đoàn.")

	def _validate_collab_vs_specialist_status(self):
		"""Người phối hợp không được Hoàn thành khi chuyên viên xử lý chưa Hoàn thành."""
		items2 = self.get("items2") or []
		for row in items2:
			if (row.trang_thai_nguoi_phoi_hop or "").strip() == "Hoàn thành" and (row.trang_thai_cv_xu_ly or "").strip() != "Hoàn thành":
				frappe.throw("Người phối hợp chỉ được chọn Hoàn thành sau khi Chuyên viên xử lý đã Hoàn thành.")

	def _validate_chair_vs_specialist_status(self):
		"""Người chủ trì chỉ được Hoàn thành khi chuyên viên xử lý và các dòng phối hợp đã Hoàn thành."""
		if (self.chairperson_status or "").strip() != "Hoàn thành":
			return

		if (self.trang_thai_chuyen_vien_xu_ly or "").strip() != "Hoàn thành":
			frappe.throw("Người chủ trì chỉ được chọn Hoàn thành sau khi Chuyên viên xử lý đã Hoàn thành.")

		items2 = self.get("items2") or []
		for row in items2:
			if (row.trang_thai_cv_xu_ly or "").strip() != "Hoàn thành" or (row.trang_thai_nguoi_phoi_hop or "").strip() != "Hoàn thành":
				frappe.throw("Người chủ trì chỉ được chọn Hoàn thành sau khi tất cả dòng phối hợp đã Hoàn thành.")

	def _validate_specialist_deadline(self):
		"""Deadline chuyên viên xử lý không được muộn hơn deadline người chủ trì."""
		if self.deadline_cv_xu_ly and self.deadline_chu_tri2:
			if getdate(self.deadline_cv_xu_ly) > getdate(self.deadline_chu_tri2):
				frappe.throw("Thời hạn Chuyên viên xử lý không được muộn hơn thời hạn Người chủ trì.")

	def _validate_items2_deadlines(self):
		"""Deadline chuyên viên xử lý (deadline2) trong bảng phối hợp không được muộn hơn deadline người phối hợp (deadline1)."""
		for row in self.get("items2") or []:
			if row.deadline2 and row.deadline1 and getdate(row.deadline2) > getdate(row.deadline1):
				frappe.throw("Thời hạn Chuyên viên xử lý không được muộn hơn thời hạn Người phối hợp.")

	def _maybe_notify_primary_specialist_assignment(self):
		"""Khi Người chủ trì gán Chuyên viên xử lý và deadline, gửi noti/ToDo/Rocket.Chat cho chuyên viên."""
		if (self.type or "").strip() != "Công văn đến":
			return
		if not (self.cv_xu_ly and self.deadline_cv_xu_ly):
			return
		if not self.name:
			return

		prev_cv = self.get_db_value("cv_xu_ly") if self.name else None
		prev_deadline = self.get_db_value("deadline_cv_xu_ly") if self.name else None
		# Chỉ gửi duy nhất lần đầu khi cả chuyên viên và deadline được gán
		if prev_cv and prev_deadline:
			return

		user_id = frappe.db.get_value("Employee", self.cv_xu_ly, "user_id")
		if not user_id:
			return

		message = f"Bạn được giao xử lý CV đến số {self.name}"

		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user_id,
				"subject": message,
				"type": "Alert",
				"document_type": self.doctype,
				"document_name": self.name,
			}
		).insert(ignore_permissions=True)

		
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"status": "Open",
				"allocated_to": user_id,
				"reference_type": self.doctype,
				"reference_name": self.name,
				"description": message,
				"priority": "Medium",
			}
		).insert(ignore_permissions=True)

		send_rocket_message(
			to_users=user_id,
			title=":bell: Công văn đến",
			message=message,
			link=get_url_to_form(self.doctype, self.name),
		)

	def _maybe_notify_chair_on_specialist_done(self):
		"""Khi chuyên viên xử lý hoàn thành, thông báo cho Người chủ trì."""
		if (self.type or "").strip() != "Công văn đến":
			return
		if not self.name:
			return

		prev_status = self.get_db_value("trang_thai_chuyen_vien_xu_ly") if self.name else None
		current_status = (self.trang_thai_chuyen_vien_xu_ly or "").strip()

		if current_status != "Hoàn thành":
			return
		if (prev_status or "").strip() == "Hoàn thành":
			return

		if not self.nguoi_chu_tri:
			return

		user_id = frappe.db.get_value("Employee", self.nguoi_chu_tri, "user_id")
		if not user_id:
			return

		message = f"{self.cv_xu_ly} đã hoàn thành xử lý CV đến số {self.name}, hãy kiểm tra công việc."

		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user_id,
				"subject": message,
				"type": "Alert",
				"document_type": self.doctype,
				"document_name": self.name,
			}
		).insert(ignore_permissions=True)

		send_rocket_message(
			to_users=user_id,
			title=":bell: Công văn đến",
			message=message,
			link=get_url_to_form(self.doctype, self.name),
		)

	def _notify_child_assignees(self):
		"""Gửi noti/ToDo/Rocket.Chat cho các nhân sự ở bảng người xử lý chính."""
		items = self.get("items") or []
		if not items:
			return

		ref = self.name
		sender = self.sender or "(Nơi gửi chưa rõ)"
		summary = self.summary or "(Chưa có trích yếu)"

		def _notify_for_role(rows, role_label):
			user_ids = set()
			for row in rows:
				if not row.employee:
					continue
				user_id = frappe.db.get_value("Employee", row.employee, "user_id")
				if user_id:
					user_ids.add(user_id)

			if not user_ids:
				return

			message = f"Bạn được giao {role_label} xử lý CV đến số {ref} {sender} {summary}"
			for user in user_ids:
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

			send_rocket_message(
				to_users=list(user_ids),
				title=":bell: Công văn đến",
				message=message,
				link=get_url_to_form(self.doctype, self.name),
			)

		chairs = [row for row in items if row.chu_tri]
		collabs = [row for row in items if row.phoi_hop]
		infos = [row for row in items if row.nhan_de_biet]

		_notify_for_role(chairs, "chủ trì xử lý")
		_notify_for_role(collabs, "phối hợp xử lý")
		_notify_for_role(infos, "nhận để biết")

	def _maybe_notify_child_assignees_on_transfer(self):
		"""Chỉ gửi thông báo cho bảng người xử lý khi trạng thái lãnh đạo chuyển sang 'Chuyển văn bản'."""
		# Chỉ áp dụng cho công văn đến
		if (self.type or "").strip() != "Công văn đến":
			return

		current = (self.handler_status or "").strip()
		if current != "Chuyển văn bản":
			return

		prev = self.get_db_value("handler_status") if self.name else None
		if (prev or "").strip() == "Chuyển văn bản":
			return

		self._notify_child_assignees()

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

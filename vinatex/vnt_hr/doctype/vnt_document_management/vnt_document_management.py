# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe
import frappe
import re
from datetime import date
from frappe.utils import getdate, nowdate, get_url_to_form, get_first_day, get_last_day
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
		self._maybe_notify_collab_specialists_assignment()
		self._maybe_notify_collab_on_spec_done()

	def after_insert(self):
		if (self.type or "").strip() != "Công văn đến":
			return

		self._notify_incoming_to_handler()
		self._notify_office_group()

	def _validate_handler_status_roles(self):
		"""Yêu cầu phải có ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết khi đặt trạng thái lãnh đạo."""
		handler_status = (getattr(self, "handler_status", None) or "").strip()
		if not handler_status:
			return

		rows = self.get("items") or []
		picked = [row for row in rows if (row.chu_tri or row.phoi_hop or row.nhan_de_biet)]
		if not picked:
			frappe.throw("Vui lòng chọn ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết trước khi cập nhật Trạng thái Lãnh đạo Tập Đoàn.")

		if handler_status == "Chuyển văn bản":
			# Chỉ bắt buộc deadline đối với Chủ trì/Phối hợp; "Nhận để biết" không cần deadline
			for row in picked:
				if (row.chu_tri or row.phoi_hop) and not row.deadline:
					frappe.throw("Dòng đã chọn vai trò Chủ trì/Phối hợp chưa có Thời hạn hoàn thành. Vui lòng nhập trước khi cập nhật Trạng thái Lãnh đạo Tập Đoàn.")

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

	def _maybe_notify_collab_specialists_assignment(self):
		"""Lần đầu gắn chuyên viên xử lý và deadline trong bảng phối hợp -> gửi thông báo cho chuyên viên phối hợp."""
		if (self.type or "").strip() != "Công văn đến":
			return
		if not self.name:
			return

		chair_dept = frappe.db.get_value("Department", self.get("items")[0].department, "department_name") if self.get("items") else None
		chair_dept = chair_dept or "(Ban chủ trì chưa rõ)"

		current_items = self.get("items2") or []
		if not current_items:
			return

		# Map existing assignments in DB to detect first-time assignment
		prev_rows = {
			row.name: row for row in frappe.get_all(
				"VNT Document Management Item",
				filters={"parent": self.name},
				fields=["name", "cv_xu_ly", "deadline2"]
			)
		}

		for row in current_items:
			if not (row.name and row.cv_xu_ly and row.deadline2):
				continue

			previous = prev_rows.get(row.name)
			# only send first time both cv_xu_ly and deadline2 exist
			if previous and previous.cv_xu_ly and previous.deadline2:
				continue

			user_id = frappe.db.get_value("Employee", row.cv_xu_ly, "user_id")
			if not user_id:
				continue

			message = f"Bạn được giao phối hợp với {chair_dept} xử lý CV đến số {self.name}"

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

	def _maybe_notify_collab_on_spec_done(self):
		"""Khi chuyên viên phối hợp (cv_xu_ly) hoàn thành, thông báo cho người phối hợp tương ứng."""
		if (self.type or "").strip() != "Công văn đến":
			return
		if not self.name:
			return

		prev_rows = {
			row.name: row for row in frappe.get_all(
				"VNT Document Management Item",
				filters={"parent": self.name},
				fields=["name", "trang_thai_cv_xu_ly"]
			)
		}

		for row in self.get("items2") or []:
			if (row.trang_thai_cv_xu_ly or "").strip() != "Hoàn thành":
				continue

			prev_status = (prev_rows.get(row.name).trang_thai_cv_xu_ly or "").strip() if prev_rows.get(row.name) else ""
			if prev_status == "Hoàn thành":
				continue

			if not row.nguoi_phoi_hop:
				continue

			user_id = frappe.db.get_value("Employee", row.nguoi_phoi_hop, "user_id")
			if not user_id:
				continue

			spec_name = row.cv_xu_ly or "(Chuyên viên phối hợp)"
			message = f"{spec_name} đã hoàn thành phối hợp xử lý CV đến số {self.name}, hãy kiểm tra công việc."

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

			message = f"Bạn được giao {role_label} CV đến số {ref} {sender} {summary}"
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

		current = (getattr(self, "handler_status", None) or "").strip()
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

		content = f"{self.sender or ''} {self.summary or ''}".strip(" /")
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


def _gather_related_doc_names(emp_name: str, emp_department: str | None = None, ignore_permissions: bool = False) -> set[str]:
	"""Tập hợp danh sách văn bản liên quan tới nhân sự (handler/chu_tri/cv_xu_ly/phối hợp/ban gửi đi)."""
	doc_names: set[str] = set()

	handler_docs = frappe.get_all(
		"VNT Document Management",
		filters={"handler": emp_name, "docstatus": ["<", 2]},
		fields=["name"],
		ignore_permissions=ignore_permissions,
	)
	doc_names.update(doc.name for doc in handler_docs)

	doc_names.update(
		row.name
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"nguoi_chu_tri": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=ignore_permissions,
		)
	)

	doc_names.update(
		row.name
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"cv_xu_ly": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=ignore_permissions,
		)
	)

	collab_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "nguoi_phoi_hop": emp_name},
		fields=["parent"],
		ignore_permissions=ignore_permissions,
	)
	collab_spec_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "cv_xu_ly": emp_name},
		fields=["parent"],
		ignore_permissions=ignore_permissions,
	)
	doc_names.update(row.parent for row in collab_rows)
	doc_names.update(row.parent for row in collab_spec_rows)

	# Công văn đi: người lập/ người ký
	outgoing_signed = frappe.get_all(
		"VNT Document Management",
		filters={"type": "Công văn đi", "nguoi_ky": emp_name, "docstatus": ["<", 2]},
		fields=["name"],
		ignore_permissions=True,
	)
	outgoing_created = frappe.get_all(
		"VNT Document Management",
		filters={"type": "Công văn đi", "employee": emp_name, "docstatus": ["<", 2]},
		fields=["name"],
		ignore_permissions=ignore_permissions,
	)
	doc_names.update(row.name for row in outgoing_signed)
	doc_names.update(row.name for row in outgoing_created)

	# Công văn đi: tất cả nhân sự thuộc Ban gửi đi đều xem được
	if emp_department:
		dept_outgoing = frappe.get_all(
			"VNT Document Management",
			filters={"type": "Công văn đi", "department": emp_department, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=True,
		)
		doc_names.update(row.name for row in dept_outgoing)

	return doc_names


def _is_leader(user: str) -> bool:
	roles = [r.lower() for r in frappe.get_roles(user)]
	return "lãnh đạo tập đoàn" in roles or "lanh dao tap doan" in roles


def _fetch_docs(doc_names: set[str], ignore_permissions: bool = False) -> dict[str, dict]:
	if not doc_names:
		return {}
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
		"employee",
		"nguoi_ky",
		"docstatus",
		"document_date",
		"received_date",
		"sender",
		"department",
		"type_doc",
	]

	try:
		rows = frappe.get_all(
			"VNT Document Management",
			filters={"name": ["in", list(doc_names)], "docstatus": ["<", 2]},
			fields=doc_fields,
			ignore_permissions=ignore_permissions,
		)
	except Exception:
		# Nếu DB chưa có đủ cột (môi trường chưa migrate), fallback tối thiểu để tránh 500
		frappe.log_error(frappe.get_traceback(), "Document Dashboard VN - fetch docs")
		rows = frappe.get_all(
			"VNT Document Management",
			filters={"name": ["in", list(doc_names)], "docstatus": ["<", 2]},
			fields=["name", "reference_number", "summary", "nguoi_chu_tri", "deadline", "modified"],
			ignore_permissions=ignore_permissions,
		)
	return {row.name: row for row in rows}


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
def trigger_handler_transfer(docname: str):
	"""
	Nút handler_status (Button) - thực hiện logic 'Chuyển văn bản' như trạng thái cũ.
	"""
	if not docname:
		frappe.throw("Thiếu tham chiếu văn bản.")

	doc = frappe.get_doc("VNT Document Management", docname)

	# Bypass fieldtype Button để chạy validate/hooks như khi đặt trạng thái
	object.__setattr__(doc, "handler_status", "Chuyển văn bản")
	doc.save(ignore_permissions=True)

	# Ghi lại xuống DB để các báo cáo/overview đọc được
	try:
		frappe.db.set_value(doc.doctype, doc.name, "handler_status", "Chuyển văn bản", update_modified=False)
	except Exception:
		frappe.log_error("Không thể cập nhật handler_status sau khi chuyển văn bản", "VNT Document Management")

	return {"name": doc.name, "handler_status": getattr(doc, "handler_status", None)}


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
		"Employee", {"user_id": user}, ["name", "employee_name", "department"], as_dict=True
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
	emp_department = emp.get("department")
	is_superviewer = emp_name == "VGT00161"
	ignore_permissions = is_superviewer

	# === Thu thập các văn bản liên quan tới nhân viên hiện tại ===
	doc_names = set()
	signed_outgoing_docs = []
	dept_outgoing_docs = []

	if is_superviewer:
		# Nhân sự đặc biệt: xem toàn bộ văn bản đang mở
		all_rows = frappe.get_all(
			"VNT Document Management",
			filters={"docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=True,
		)
		doc_names.update(row.name for row in all_rows)

	# Lãnh đạo (handler)
	handler_docs = frappe.get_all(
		"VNT Document Management",
		filters={"handler": emp_name, "docstatus": ["<", 2]},
		fields=["name", "reference_number", "summary", "nguoi_chu_tri"],
		ignore_permissions=ignore_permissions,
	)
	doc_names.update(doc.name for doc in handler_docs)

	# Người chủ trì
	doc_names.update(
		row.name
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"nguoi_chu_tri": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=ignore_permissions,
		)
	)

	# Chuyên viên xử lý chính
	doc_names.update(
		row.name
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"cv_xu_ly": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=ignore_permissions,
		)
	)

	# Người ký/Gửi công văn đi
	signed_outgoing_docs = frappe.get_all(
		"VNT Document Management",
		filters={"type": "Công văn đi", "nguoi_ky": emp_name, "docstatus": ["<", 2]},
		fields=["name"],
		ignore_permissions=True,
	)
	doc_names.update(row.name for row in signed_outgoing_docs)
	doc_names.update(
		row.name
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"type": "Công văn đi", "employee": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=ignore_permissions,
		)
	)
	if emp_department:
		dept_outgoing_docs = frappe.get_all(
			"VNT Document Management",
			filters={"type": "Công văn đi", "department": emp_department, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=True,
		)
		doc_names.update(row.name for row in dept_outgoing_docs)

	# Người phối hợp / chuyên viên phối hợp (từ child table)
	collab_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "nguoi_phoi_hop": emp_name},
		fields=["parent", "deadline1", "trang_thai_nguoi_phoi_hop"],
		ignore_permissions=ignore_permissions,
	)
	collab_spec_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "cv_xu_ly": emp_name},
		fields=["parent", "deadline2", "trang_thai_cv_xu_ly"],
		ignore_permissions=ignore_permissions,
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
		"employee",
		"nguoi_ky",
		"docstatus",
		"department",
	]
	doc_fetch_ignore_permissions = ignore_permissions or bool(signed_outgoing_docs) or bool(dept_outgoing_docs)
	docs = {
		row.name: row
		for row in frappe.get_all(
			"VNT Document Management",
			filters={"name": ["in", list(doc_names)]},
			fields=doc_fields,
			ignore_permissions=doc_fetch_ignore_permissions,
		)
	}

	# Dữ liệu child dùng cho phân loại/pending
	handler_docs = frappe.get_all(
		"VNT Document Management",
		filters={"handler": emp_name, "docstatus": ["<", 2]},
		fields=["name", "reference_number", "summary", "nguoi_chu_tri"],
		ignore_permissions=ignore_permissions,
	)
	collab_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "nguoi_phoi_hop": emp_name},
		fields=["parent", "deadline1", "trang_thai_nguoi_phoi_hop"],
		ignore_permissions=ignore_permissions,
	)
	collab_spec_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parenttype": "VNT Document Management", "cv_xu_ly": emp_name},
		fields=["parent", "deadline2", "trang_thai_cv_xu_ly"],
		ignore_permissions=ignore_permissions,
	)

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

	def _outgoing_status(doc):
		if getattr(doc, "docstatus", None) == 1:
			return "Hoàn thành"
		if getattr(doc, "docstatus", None) == 2:
			return "Trả lại"
		return ""

	assignments = []
	seen_assignments = set()

	def _add_assignment(docname, role, status=None, deadline=None):
		doc = docs.get(docname)
		if not doc:
			return
		key = (docname, role)
		if key in seen_assignments:
			return
		seen_assignments.add(key)
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
		if doc.type == "Công văn đi":
			if getattr(doc, "employee", None) == emp_name:
				_add_assignment(name, "Người lập", _outgoing_status(doc))
			if getattr(doc, "nguoi_ky", None) == emp_name:
				_add_assignment(name, "Người ký", _outgoing_status(doc))
			if emp_department and getattr(doc, "department", None) == emp_department:
				_add_assignment(name, "Ban gửi đi", _outgoing_status(doc))
			if (doc.type_doc or "").strip().upper() == "QĐ":
				_add_assignment(name, "Quyết định", _outgoing_status(doc))

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
				ignore_permissions=ignore_permissions,
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

	assigned_top = _top(assigned_list)
	pending_top = _top(pending_assignment)
	completed_top = _top(completed_list)
	overdue_top = _top(overdue_list)

	return {
		"employee": emp,
		"counts": {
			"assigned": len(assigned_top),
			"pending_assignment": len(pending_top),
			"completed": len(completed_top),
			"overdue": len(overdue_top),
		},
		"lists": {
			"assigned": assigned_top,
			"pending_assignment": pending_top,
			"completed": completed_top,
			"overdue": overdue_top,
		},
	}


def _all_done(status_list: list[str]) -> bool:
	return bool(status_list) and all(("hoàn" in s.lower()) or ("done" in s.lower()) for s in status_list if s)


def _has_value(status_list: list[str], needle: str) -> bool:
	needle = (needle or "").lower()
	return any(needle in (s or "").lower() for s in status_list)


def _derive_status(parent_status: str, child_statuses: list[str]) -> str:
	parent_status = (parent_status or "").lower()
	child_statuses = [(s or "").lower() for s in child_statuses if s is not None]

	if _all_done(child_statuses) and ("hoàn" in parent_status or "done" in parent_status):
		return "Hoàn thành"
	if _has_value(child_statuses + [parent_status], "trả"):
		return "Trả lại"
	if any(not s for s in child_statuses) or not parent_status:
		return "Chưa giao"
	return "Đang xử lý"


@frappe.whitelist()
def get_document_dashboard_vn():
	"""
	Bộ dữ liệu tiếng Việt cho dashboard quản lý văn bản:
	- KPI: hoàn thành / còn lại
	- Pie theo trạng thái
	- Bảng văn bản: số, chủ trì, deadline, trạng thái
	"""
	user = frappe.session.user
	is_leader = _is_leader(user)
	emp = frappe.db.get_value(
		"Employee", {"user_id": user}, ["name", "employee_name", "department"], as_dict=True
	)
	is_superviewer = bool(emp and emp.get("name") == "VGT00161")

	if not emp and not is_leader and not is_superviewer:
		return {
			"employee": None,
			"counts": {"completed": 0, "incomplete": 0},
			"status_pie": [],
			"documents": [],
			"message": "Không tìm thấy Employee gắn với user hiện tại",
		}

	# Nếu là lãnh đạo tập đoàn hoặc superviewer: thấy toàn bộ văn bản (đang mở)
	if is_leader or is_superviewer:
		doc_names = {
			row.name
			for row in frappe.get_all(
				"VNT Document Management",
				filters={"docstatus": ["<", 2]},
				fields=["name"],
				limit=500,
				ignore_permissions=True,
			)
		}
		docs = _fetch_docs(doc_names, ignore_permissions=True)
	else:
		signed_outgoing_docs = frappe.get_all(
			"VNT Document Management",
			filters={"type": "Công văn đi", "nguoi_ky": emp.name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=True,
		)
		doc_names = _gather_related_doc_names(emp.name, emp.get("department"))
		doc_names.update(row.name for row in signed_outgoing_docs)
		docs = _fetch_docs(doc_names, ignore_permissions=bool(signed_outgoing_docs))
	if not doc_names:
		return {
			"employee": emp,
			"counts": {"completed": 0, "incomplete": 0},
			"status_pie": [],
			"documents": [],
		}

	# items = VNT Document Management Item2 (lấy người chủ trì, deadline)
	chair_rows = frappe.get_all(
		"VNT Document Management Item2",
		filters={"parent": ["in", list(doc_names)], "chu_tri": 1},
		fields=["parent", "employee", "deadline"],
		ignore_permissions=is_leader,
	)
	chair_emp_ids = {r.employee for r in chair_rows if r.get("employee")}
	chair_emp_map = (
		{
			r.name: r.employee_name
			for r in frappe.get_all(
				"Employee",
				filters={"name": ["in", list(chair_emp_ids)]},
				fields=["name", "employee_name"],
				ignore_permissions=is_leader,
			)
		}
		if chair_emp_ids
		else {}
	)
	chair_map = {r.parent: r for r in chair_rows}

	# items2 = VNT Document Management Item (trạng thái xử lý)
	item_status_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parent": ["in", list(doc_names)]},
		fields=["parent", "trang_thai_cv_xu_ly", "trang_thai_nguoi_phoi_hop"],
		ignore_permissions=is_leader,
	)
	status_by_parent: dict[str, list[str]] = {}
	for row in item_status_rows:
		if row.trang_thai_cv_xu_ly:
			status_by_parent.setdefault(row.parent, []).append(row.trang_thai_cv_xu_ly)
		if row.trang_thai_nguoi_phoi_hop:
			status_by_parent.setdefault(row.parent, []).append(row.trang_thai_nguoi_phoi_hop)

	status_counts = {"Hoàn thành": 0, "Đang xử lý": 0, "Chưa giao": 0, "Trả lại": 0}
	doc_rows: list[dict] = []

	for name, doc in docs.items():
		child_statuses = status_by_parent.get(name) or []
		status_label = _derive_status(doc.get("trang_thai_chuyen_vien_xu_ly"), child_statuses)
		if status_label == "Chưa giao" and chair_map.get(name):
			status_label = "Đang xử lý"
		if status_label in status_counts:
			status_counts[status_label] += 1

		# Loại hiển thị (Quyết định nếu type_doc = QĐ)
		raw_type = doc.get("type")
		type_doc = (doc.get("type_doc") or "").strip().upper()
		display_type = raw_type
		if raw_type == "Công văn đi" and type_doc == "QĐ":
			display_type = "Quyết định"

		chair = chair_map.get(name) or {}
		chair_name = chair_emp_map.get(chair.get("employee")) if chair else None
		deadline = (
			chair.get("deadline")
			or doc.get("deadline")
			or doc.get("deadline_chu_tri2")
			or doc.get("deadline_cv_xu_ly")
		)

		doc_rows.append(
			{
				"name": name,
				"reference_number": doc.get("reference_number") or name,
				"summary": doc.get("summary"),
				"type": display_type,
				"document_date": str(doc.get("document_date") or "") if doc.get("document_date") else "",
				"received_date": str(doc.get("received_date") or "") if doc.get("received_date") else "",
				"sender": doc.get("sender"),
				"chairperson": chair_name
					or chair.get("employee")
					or chair.get("employee_name")
					or doc.get("nguoi_chu_tri"),
				"deadline": str(deadline) if deadline else "",
				"status": status_label,
			}
		)


	completed = status_counts["Hoàn thành"]
	total = sum(status_counts.values())
	incomplete = max(total - completed, 0)

	status_pie = [{"name": k, "value": v} for k, v in status_counts.items()]
	doc_rows.sort(key=lambda r: r.get("deadline") or "")

	return {
		"employee": emp,
		"counts": {"completed": completed, "incomplete": incomplete, "statuses": status_counts},
		"status_pie": status_pie,
		"documents": doc_rows,
	}


@frappe.whitelist()
def get_next_reference_number(
	department: str | None = None, document_date: str | None = None, type_doc: str | None = None
) -> str | None:
	"""Return next incremental reference number for outgoing documents of a department, reset each year."""
	if not department:
		return None

	doc_date = getdate(document_date) if document_date else getdate(nowdate())
	year = doc_date.year
	year_start = get_first_day(date(year, 1, 1))
	year_end = get_last_day(date(year, 12, 1))

	abbr = frappe.db.get_value("Department", department, "custom_short_text_qlvb") or ""
	abbr = (abbr or "").strip()
	existing_refs = frappe.get_all(
		"VNT Document Management",
		filters={
			"type": "Công văn đi",
			"department": department,
			"docstatus": ["<", 2],
			"document_date": ["between", [year_start, year_end]],
			"type_doc": type_doc if type_doc else ["in", ["", None]],
		},
		fields=["reference_number"],
	)

	max_num = 0
	max_width = 0
	pattern = (
		re.compile(r"(\d+)(?!.*\d)")
	)

	for row in existing_refs:
		ref = (row.reference_number or "").strip()
		if not ref:
			continue
		match = pattern.search(ref) if pattern else None
		if not match:
			match = re.search(r"(\d+)(?!.*\d)", ref)
		if not match:
			continue
		num_str = match.group(1)
		num_val = int(num_str)
		max_num = max(max_num, num_val)
		max_width = max(max_width, len(num_str))

	next_num = max_num + 1
	width = max_width  # giữ padding theo dữ liệu cũ (nếu có), mặc định không ép 3 chữ số
	render_num = str(next_num).zfill(width) if width else str(next_num)
	type_doc = (type_doc or "").strip()

	if type_doc:
		return f"{render_num}/{type_doc}-TĐDMVN"

	# type_doc trống: dùng abbr nếu có
	if abbr:
		return f"{render_num}/TĐDMVN-{abbr}"
	return f"{render_num}/TĐDMVN"

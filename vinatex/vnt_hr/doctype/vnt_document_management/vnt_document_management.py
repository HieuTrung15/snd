# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe
import frappe
import re
from datetime import date
from frappe.utils import getdate, nowdate, get_url_to_form, get_first_day, get_last_day,cint
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
		self._maybe_close_handler_todo_on_transfer()
		self._maybe_close_specialist_todo_on_done()
		self._maybe_close_chair_todo_on_done()
		self._maybe_close_collab_todos_on_done()

	def after_insert(self):
		doc_type = (self.type or "").strip()
		if doc_type == "Công văn đến":
			self._notify_incoming_to_handler()
			self._notify_office_group()
		elif doc_type == "Công văn đi":
			self._notify_outgoing_department_members()

	def _validate_handler_status_roles(self):
		"""Yêu cầu phải có ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết khi đặt trạng thái lãnh đạo."""
		handler_status = (getattr(self, "handler_status", None) or "").strip()
		if not handler_status:
			return

		rows = []
		rows.extend(self.get("items") or [])
		rows.extend(self.get("item2") or [])
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
			# Nếu chưa giao chuyên viên phối hợp, cho phép người phối hợp tự hoàn thành
			if not (row.cv_xu_ly or "").strip():
				continue

			if (row.trang_thai_nguoi_phoi_hop or "").strip() == "Hoàn thành" and (row.trang_thai_cv_xu_ly or "").strip() != "Hoàn thành":
				frappe.throw("Người phối hợp chỉ được chọn Hoàn thành sau khi Chuyên viên xử lý đã Hoàn thành.")

	def _validate_chair_vs_specialist_status(self):
		"""Người chủ trì chỉ được Hoàn thành khi chuyên viên xử lý và các dòng phối hợp đã Hoàn thành."""
		if (self.chairperson_status or "").strip() != "Hoàn thành":
			return

		# Nếu đã gán chuyên viên chính thì yêu cầu Hoàn thành; nếu chưa gán thì bỏ qua điều kiện này
		if self.cv_xu_ly and (self.trang_thai_chuyen_vien_xu_ly or "").strip() != "Hoàn thành":
			frappe.throw("Người chủ trì chỉ được chọn Hoàn thành sau khi Chuyên viên xử lý đã Hoàn thành.")

		items2 = self.get("items2") or []
		for row in items2:
			# Người phối hợp phải Hoàn thành
			if (row.trang_thai_nguoi_phoi_hop or "").strip() != "Hoàn thành":
				frappe.throw("Người chủ trì chỉ được chọn Hoàn thành sau khi tất cả dòng phối hợp đã Hoàn thành.")
			# Nếu dòng có chuyên viên phối hợp, yêu cầu chuyên viên phối hợp cũng Hoàn thành
			if row.cv_xu_ly and (row.trang_thai_cv_xu_ly or "").strip() != "Hoàn thành":
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

	def _close_todos_for_user(self, user_id: str | None):
		"""Close open ToDos for this doc allocated to given user."""
		if not user_id:
			return

		todos = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": self.doctype,
				"reference_name": self.name,
				"allocated_to": user_id,
				"status": ["!=", "Cancelled"],
			},
			fields=["name", "status"],
			ignore_permissions=True,
		)

		for row in todos:
			if (row.status or "").strip().lower() == "closed":
				continue
			frappe.db.set_value("ToDo", row.name, "status", "Closed", update_modified=False)

	def _maybe_close_handler_todo_on_transfer(self):
		"""
		Khi lãnh đạo bấm 'Chuyển văn bản' và đã tick 'Đã chuyển xử lý',
		đóng ToDo được tạo lúc nhận công văn đến cho Lãnh đạo Tập đoàn.
		"""
		if (self.type or "").strip() != "Công văn đến":
			return

		current_status = (getattr(self, "handler_status", None) or "").strip()
		if current_status != "Chuyển văn bản":
			return

		if not self.name or not self.handler:
			return

		user_id = frappe.db.get_value("Employee", self.handler, "user_id")
		if not user_id:
			return
		self._close_todos_for_user(user_id)

	def _maybe_close_specialist_todo_on_done(self):
		"""
		Khi chuyên viên xử lý chính Hoàn thành, đóng ToDo đã giao cho chuyên viên này.
		"""
		if (self.type or "").strip() != "Công văn đến":
			return
		if not self.name or not self.cv_xu_ly:
			return

		current_status = (getattr(self, "trang_thai_chuyen_vien_xu_ly", None) or "").strip()
		if current_status != "Hoàn thành":
			return

		prev_status = (self.get_db_value("trang_thai_chuyen_vien_xu_ly") or "").strip() if self.name else ""
		if prev_status == "Hoàn thành":
			return

		user_id = frappe.db.get_value("Employee", self.cv_xu_ly, "user_id")
		if not user_id:
			return
		self._close_todos_for_user(user_id)

	def _maybe_close_chair_todo_on_done(self):
		"""
		Khi Người chủ trì Hoàn thành, đóng ToDo đã giao cho Người chủ trì.
		"""
		if (self.type or "").strip() != "Công văn đến":
			return
		if not self.name or not self.nguoi_chu_tri:
			return

		current_status = (getattr(self, "chairperson_status", None) or "").strip()
		if current_status != "Hoàn thành":
			return

		prev_status = (self.get_db_value("chairperson_status") or "").strip() if self.name else ""
		if prev_status == "Hoàn thành":
			return

		user_id = frappe.db.get_value("Employee", self.nguoi_chu_tri, "user_id")
		if not user_id:
			return
		self._close_todos_for_user(user_id)

	def _maybe_close_collab_todos_on_done(self):
		"""
		Khi Người phối hợp hoặc Chuyên viên phối hợp (items2) Hoàn thành, đóng ToDo tương ứng.
		"""
		if (self.type or "").strip() != "Công văn đến":
			return
		if not self.name:
			return

		prev_rows = {
			row.name: row
			for row in frappe.get_all(
				"VNT Document Management Item",
				filters={"parent": self.name},
				fields=["name", "trang_thai_nguoi_phoi_hop", "trang_thai_cv_xu_ly"],
				ignore_permissions=True,
			)
		}

		for row in self.get("items2") or []:
			# Người phối hợp
			if (row.trang_thai_nguoi_phoi_hop or "").strip() == "Hoàn thành":
				prev_status = (prev_rows.get(row.name).trang_thai_nguoi_phoi_hop or "").strip() if prev_rows.get(row.name) else ""
				if prev_status != "Hoàn thành" and row.nguoi_phoi_hop:
					user_id = frappe.db.get_value("Employee", row.nguoi_phoi_hop, "user_id")
					self._close_todos_for_user(user_id)

			# Chuyên viên phối hợp
			if (row.trang_thai_cv_xu_ly or "").strip() == "Hoàn thành":
				prev_spec_status = (prev_rows.get(row.name).trang_thai_cv_xu_ly or "").strip() if prev_rows.get(row.name) else ""
				if prev_spec_status != "Hoàn thành" and row.cv_xu_ly:
					user_id = frappe.db.get_value("Employee", row.cv_xu_ly, "user_id")
					self._close_todos_for_user(user_id)

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

		message = f"Bạn được giao xử lý CV đến số {self.reference_number}"

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
		items.extend(self.get("item2") or [])
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
			
			# frappe.get_doc(
			# 	{
			# 		"doctype": "ToDo",
			# 		"status": "Open",
			# 		"allocated_to": user,
			# 		"reference_type": self.doctype,
			# 		"reference_name": self.name,
			# 		"description": message,
			# 		"priority": "Medium",
			# 	}
			# ).insert(ignore_permissions=True)

		# Rocket.Chat
		send_rocket_message(
			to_users=user_list,
			title=":bell: Thông báo Công văn đến",
			message=message,
			link=get_url_to_form(self.doctype, self.name),
		)

	def _notify_outgoing_department_members(self):
		"""Gửi thông báo công văn đi tới toàn bộ nhân sự thuộc Ban gửi đi."""
		if (self.type or "").strip() != "Công văn đi":
			return
		if not self.department or not self.name:
			return

		emp_rows = frappe.get_all(
			"Employee",
			filters={"department": self.department},
			fields=["name", "employee_name", "user_id"],
		)
		user_ids = [r.user_id for r in emp_rows if r.user_id]
		if not user_ids:
			return

		dept_name = frappe.db.get_value("Department", self.department, "department_name") or self.department
		ref = self.reference_number or self.name
		message = f"{dept_name} vừa ban hành Công văn đi số {ref}"

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

		send_rocket_message(
			to_users=user_ids,
			title=":bell: Công văn đi",
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


def _resolve_company_for_leadership(company: str | None = None) -> str | None:
	if company:
		return company

	default_company = frappe.defaults.get_user_default("Company")
	if default_company:
		return default_company

	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "company")


def _map_company_leadership_rows(rows: list | None) -> list[dict]:
	result = []
	for row in rows or []:
		result.append(
			{
				"employee": row.employee,
				"department": row.department,
				"deadline": row.deadline,
				"chu_tri": row.chu_tri,
				"phoi_hop": row.phoi_hop,
				"nhan_de_biet": row.nhan_de_biet,
			}
		)
	return result


@frappe.whitelist()
def get_company_leadership(company: str | None = None):
	"""Return leadership rows from Company custom tables for incoming documents."""
	resolved_company = _resolve_company_for_leadership(company)
	if not resolved_company:
		return {"cap_cao": [], "cap_trung": []}

	try:
		company_doc = frappe.get_doc("Company", resolved_company)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "VNT Document Management - Company leadership")
		return {"cap_cao": [], "cap_trung": []}

	return {
		"cap_cao": _map_company_leadership_rows(company_doc.get("custom_ld_cap_cao")),
		"cap_trung": _map_company_leadership_rows(company_doc.get("custom_ld_cap_trung")),
	}


@frappe.whitelist()
def get_employee_display_names(employee_ids):
	ids = employee_ids
	if isinstance(employee_ids, str):
		ids = frappe.parse_json(employee_ids)
	if not ids:
		return {}
	if not isinstance(ids, (list, tuple, set)):
		ids = [ids]

	cleaned = []
	seen = set()
	for emp_id in ids:
		if not emp_id:
			continue
		emp_id = str(emp_id).strip()
		if not emp_id or emp_id in seen:
			continue
		seen.add(emp_id)
		cleaned.append(emp_id)

	if not cleaned:
		return {}

	rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", cleaned]},
		fields=["name", "employee_name"],
		ignore_permissions=True,
	)

	mapping = {row.name: (row.employee_name or row.name) for row in rows}
	for emp_id in cleaned:
		mapping.setdefault(emp_id, emp_id)
	return mapping


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
	if not getattr(doc, "handler_transferred_at", None):
		object.__setattr__(doc, "handler_transferred_at", frappe.utils.now_datetime())
	doc.save(ignore_permissions=True)

	# Ghi lại xuống DB để các báo cáo/overview đọc được
	try:
		frappe.db.set_value(doc.doctype, doc.name, "handler_status", "Chuyển văn bản", update_modified=False)
	except Exception:
		frappe.log_error("Không thể cập nhật handler_status sau khi chuyển văn bản", "VNT Document Management")

	# Đóng ToDo của Lãnh đạo (nếu có)
	if doc.handler:
		user_id = frappe.db.get_value("Employee", doc.handler, "user_id")
		if user_id:
			doc._close_todos_for_user(user_id)

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
@frappe.whitelist()
def get_document_overview(limit: int = 6):
	"""
	Tổng hợp nhanh 4 nhóm việc cần theo dõi cho Custom HTML Block "Quản lý văn bản":
	- assigned: Việc đã được giao cho tôi (còn đang mở)
	- pending_assignment: Văn bản tôi là Lãnh đạo nhưng chưa giao Người chủ trì
	- completed: Việc tôi đã hoàn thành
	- overdue: Việc của tôi đã quá hạn (chưa hoàn thành)

	NOTE:
	- counts: là tổng thực tế
	- lists: trả về top `limit` phần tử để UI render nhanh
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

	from frappe.utils import getdate, nowdate

	today = getdate(nowdate())
	emp_name = emp.name
	emp_department = emp.get("department")

	# Superviewer: xem toàn bộ văn bản đang mở
	is_superviewer = emp_name == "VGT00161"
	ignore_permissions = is_superviewer

	# === Thu thập các văn bản liên quan tới nhân viên hiện tại ===
	doc_names = set()
	signed_outgoing_docs = []
	dept_outgoing_docs = []

	if is_superviewer:
		all_rows = frappe.get_all(
			"VNT Document Management",
			filters={"docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=True,
		)
		doc_names.update(r.name for r in all_rows)

	# Lãnh đạo (handler)
	handler_docs = frappe.get_all(
		"VNT Document Management",
		filters={"handler": emp_name, "docstatus": ["<", 2]},
		fields=["name", "reference_number", "summary", "nguoi_chu_tri"],
		ignore_permissions=ignore_permissions,
	)
	doc_names.update(d.name for d in handler_docs)

	# Người chủ trì
	doc_names.update(
		r.name
		for r in frappe.get_all(
			"VNT Document Management",
			filters={"nguoi_chu_tri": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=ignore_permissions,
		)
	)

	# Chuyên viên xử lý chính
	doc_names.update(
		r.name
		for r in frappe.get_all(
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
	doc_names.update(r.name for r in signed_outgoing_docs)

	doc_names.update(
		r.name
		for r in frappe.get_all(
			"VNT Document Management",
			filters={"type": "Công văn đi", "employee": emp_name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=ignore_permissions,
		)
	)

	# Công văn đi: tất cả nhân sự thuộc Ban gửi đi đều xem được
	if emp_department:
		dept_outgoing_docs = frappe.get_all(
			"VNT Document Management",
			filters={"type": "Công văn đi", "department": emp_department, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=True,
		)
		doc_names.update(r.name for r in dept_outgoing_docs)

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
	doc_names.update(r.parent for r in collab_rows)
	doc_names.update(r.parent for r in collab_spec_rows)
	if not doc_names:
		return {
			"employee": emp,
			"counts": {"assigned": 0, "pending_assignment": 0, "completed": 0, "overdue": 0},
			"lists": {"assigned": [], "pending_assignment": [], "completed": [], "overdue": []},
		}

	# === Fetch docs để render UI ===
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
		"type_doc",
	]

	doc_fetch_ignore_permissions = ignore_permissions or bool(signed_outgoing_docs) or bool(dept_outgoing_docs)
	docs = {
		r.name: r
		for r in frappe.get_all(
			"VNT Document Management",
			filters={"name": ["in", list(doc_names)]},
			fields=doc_fields,
			ignore_permissions=doc_fetch_ignore_permissions,
		)
	}

	# Map child rows theo parent
	collab_by_parent = {}
	for r in collab_rows:
		collab_by_parent.setdefault(r.parent, []).append(r)

	collab_spec_by_parent = {}
	for r in collab_spec_rows:
		collab_spec_by_parent.setdefault(r.parent, []).append(r)

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

	# Vai trò theo doc
	for name, doc in docs.items():
		if doc.nguoi_chu_tri == emp_name:
			_add_assignment(name, "Người chủ trì", doc.chairperson_status, doc.deadline_chu_tri2)
		if doc.cv_xu_ly == emp_name:
			_add_assignment(name, "Chuyên viên xử lý", doc.trang_thai_chuyen_vien_xu_ly, doc.deadline_cv_xu_ly)

		# Công văn đi / Quyết định
		if doc.type == "Công văn đi":
			if getattr(doc, "employee", None) == emp_name:
				_add_assignment(name, "Người lập", _outgoing_status(doc))
			if getattr(doc, "nguoi_ky", None) == emp_name:
				_add_assignment(name, "Người ký", _outgoing_status(doc))
			if emp_department and getattr(doc, "department", None) == emp_department:
				_add_assignment(name, "Ban gửi đi", _outgoing_status(doc))
			if (doc.type_doc or "").strip().upper() == "QĐ":
				_add_assignment(name, "Quyết định", _outgoing_status(doc))

	# Vai trò từ child
	for rows in collab_by_parent.values():
		for item in rows:
			_add_assignment(item.parent, "Người phối hợp", item.trang_thai_nguoi_phoi_hop, item.deadline1)

	for rows in collab_spec_by_parent.values():
		for item in rows:
			_add_assignment(item.parent, "Chuyên viên phối hợp", item.trang_thai_cv_xu_ly, item.deadline2)

	assigned_list = [a for a in assignments if not _is_completed(a.get("status"))]
	completed_list = [a for a in assignments if _is_completed(a.get("status"))]
	overdue_list = [a for a in assignments if a.get("overdue")]

	# === pending_assignment: Văn bản handler nhưng chưa giao Người chủ trì ===
	handler_doc_names = {d.name for d in handler_docs}
	has_chair = set()
	if handler_doc_names:
		has_chair = {
			r.parent
			for r in frappe.get_all(
				"VNT Document Management Item2",
				filters={"parent": ["in", list(handler_doc_names)], "chu_tri": 1},
				fields=["parent"],
				distinct=True,
				ignore_permissions=ignore_permissions,
			)
		}

	pending_assignment = []
	for d in handler_docs:
		if d.nguoi_chu_tri or d.name in has_chair:
			continue
		full_doc = docs.get(d.name)
		pending_assignment.append(
			{
				"docname": d.name,
				"reference_number": d.reference_number,
				"summary": (full_doc.summary if full_doc else d.summary),
			}
		)

	# === Trả về: counts = tổng; lists = top N ===
	def _top(lst):
		return (lst or [])[: int(limit or 6)]

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

	status_counts = {"Hoàn thành": 0, "Đang xử lý": 0, "Quá hạn": 0, "Trả lại": 0}
	doc_rows: list[dict] = []
	today = getdate(nowdate())

	for name, doc in docs.items():
		status_label = _block_compute_status(doc, today=today)
		if status_label not in status_counts:
			status_label = "Đang xử lý"
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
	"""
	Return next incremental reference number for outgoing documents, shared across all departments/type_doc per year.
	"""

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
			"docstatus": ["<", 2],
			"document_date": ["between", [year_start, year_end]],
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

@frappe.whitelist()
def get_document_kpis_v2():
	"""
	KPI  Custom HTML Block:
	- total_visible: tổng số văn bản user nhìn thấy trên UI (theo logic liên quan/leader/superviewer)
	- incoming_completed: số Công văn đến có trạng thái Hoàn thành
	- incoming_processing: số Công văn đến có trạng thái Đang xử lý
	- incoming_overdue: số Công văn đến bị Quá hạn (deadline < today và chưa hoàn thành)
	"""
	user = frappe.session.user
	emp = frappe.db.get_value(
		"Employee", {"user_id": user}, ["name", "employee_name", "department"], as_dict=True
	)

	is_leader = _is_leader(user)
	is_superviewer = bool(emp and emp.get("name") == "VGT00161")

	# Nếu không có Employee mà không phải leader/superviewer -> trả 0
	if not emp and not is_leader and not is_superviewer:
		return {
			"employee": None,
			"counts": {"total_visible": 0, "incoming_completed": 0, "incoming_processing": 0, "incoming_overdue": 0},
			"message": "Không tìm thấy Employee gắn với user hiện tại",
		}

	# === 1) Tập hợp doc_names user nhìn thấy ===
	if is_leader or is_superviewer:
		doc_names = {
			r.name
			for r in frappe.get_all(
				"VNT Document Management",
				filters={"docstatus": ["<", 2]},
				fields=["name"],
				limit=2000,
				ignore_permissions=True,
			)
		}
		docs = _fetch_docs(doc_names, ignore_permissions=True)
	else:
		# Công văn đi: người ký có thể xem (ignore_permissions=True)
		signed_outgoing = frappe.get_all(
			"VNT Document Management",
			filters={"type": "Công văn đi", "nguoi_ky": emp.name, "docstatus": ["<", 2]},
			fields=["name"],
			ignore_permissions=True,
		)

		doc_names = _gather_related_doc_names(emp.name, emp.get("department"))
		doc_names.update(r.name for r in signed_outgoing)

		# Nếu có signed_outgoing thì fetch ignore_permissions để khỏi rớt quyền
		docs = _fetch_docs(doc_names, ignore_permissions=bool(signed_outgoing))

	total_visible = len(doc_names)
	if not doc_names:
		return {
			"employee": emp,
			"counts": {"total_visible": 0, "incoming_completed": 0, "incoming_processing": 0, "incoming_overdue": 0},
		}

	# === 2) Lọc Công văn đến ===
	incoming_names = [name for name, d in (docs or {}).items() if (d.get("type") or "").strip() == "Công văn đến"]
	if not incoming_names:
		return {
			"employee": emp,
			"counts": {"total_visible": total_visible, "incoming_completed": 0, "incoming_processing": 0, "incoming_overdue": 0},
		}

	from frappe.utils import getdate, nowdate
	today = getdate(nowdate())

	# chair_rows: lấy deadline chủ trì nếu có (chu_tri=1)
	chair_rows = frappe.get_all(
		"VNT Document Management Item2",
		filters={"parent": ["in", incoming_names], "chu_tri": 1},
		fields=["parent", "deadline"],
		ignore_permissions=True,
	)
	chair_map = {r.parent: r for r in chair_rows}

	# status ở items2 (bảng phối hợp)
	item_status_rows = frappe.get_all(
		"VNT Document Management Item",
		filters={"parent": ["in", incoming_names]},
		fields=["parent", "trang_thai_cv_xu_ly", "trang_thai_nguoi_phoi_hop"],
		ignore_permissions=True,
	)
	status_by_parent: dict[str, list[str]] = {}
	for r in item_status_rows:
		if r.trang_thai_cv_xu_ly:
			status_by_parent.setdefault(r.parent, []).append(r.trang_thai_cv_xu_ly)
		if r.trang_thai_nguoi_phoi_hop:
			status_by_parent.setdefault(r.parent, []).append(r.trang_thai_nguoi_phoi_hop)

	# doc có “đã giao chủ trì” hay chưa (để Chưa giao -> Đang xử lý)
	has_chair = set()
	has_chair.update(chair_map.keys())

	def _best_deadline(docname: str, doc: dict):
		chair = chair_map.get(docname) or {}
		return (
			chair.get("deadline")
			or doc.get("deadline")
			or doc.get("deadline_chu_tri2")
			or doc.get("deadline_cv_xu_ly")
		)

	incoming_completed = 0
	incoming_processing = 0
	incoming_overdue = 0

	for name in incoming_names:
		doc = docs.get(name) or {}
		child_statuses = status_by_parent.get(name) or []

		status_label = _derive_status(doc.get("trang_thai_chuyen_vien_xu_ly"), child_statuses)
		if status_label == "Chưa giao" and name in has_chair:
			status_label = "Đang xử lý"

		deadline_val = _best_deadline(name, doc)
		try:
			dl = getdate(deadline_val) if deadline_val else None
		except Exception:
			dl = None

		# Derive Quá hạn
		if dl and dl < today and status_label != "Hoàn thành":
			status_label = "Quá hạn"

		if status_label == "Hoàn thành":
			incoming_completed += 1
		elif status_label == "Đang xử lý":
			incoming_processing += 1
		elif status_label == "Quá hạn":
			incoming_overdue += 1

	return {
		"employee": emp,
		"counts": {
			"total_visible": total_visible,
			"incoming_completed": incoming_completed,
			"incoming_processing": incoming_processing,
			"incoming_overdue": incoming_overdue,
		},
	}

# ===== Custom HTML Block API (v2) =====
# KPI + danh sách dùng chung 1 logic trạng thái, chỉ tính 3 loại: Công văn đến/đi/Quyết định

import frappe
from frappe.utils import getdate, nowdate, cint

_ALLOWED_BLOCK_TYPES = ("Công văn đến", "Công văn đi", "Quyết định")


def _block_best_deadline(d: dict):
	return d.get("deadline_chu_tri2") or d.get("deadline_cv_xu_ly") or d.get("deadline")


def _block_normalize_status(raw: str) -> str:
	s = (raw or "").strip()
	low = s.lower()

	if not s:
		return "Đang xử lý"
	if "hoàn" in low or "done" in low:
		return "Hoàn thành"
	if "trả" in low:
		return "Trả lại"
	if "quá" in low or "over" in low:
		return "Quá hạn"
	return "Đang xử lý"


def _block_compute_status(doc: dict, today=None) -> str:
	today = today or getdate(nowdate())

	# Công văn đi + Quyết định (lưu dạng Công văn đi + type_doc=QĐ)
	is_outgoing_or_qd = (doc.get("type") == "Công văn đi") or ((doc.get("type_doc") or "").strip().upper() == "QĐ")
	if is_outgoing_or_qd:
		return "Hoàn thành" if int(doc.get("docstatus") or 0) == 1 else "Đang xử lý"

	# Công văn đến: giữ logic cũ + quá hạn theo deadline
	raw = (doc.get("chairperson_status") or doc.get("trang_thai_chuyen_vien_xu_ly") or "")
	st = _block_normalize_status(raw)

	try:
		dl_val = _block_best_deadline(doc)
		dl = getdate(dl_val) if dl_val else None
	except Exception:
		dl = None

	if dl and dl < today and st not in ("Hoàn thành", "Trả lại"):
		return "Quá hạn"
	return st


@frappe.whitelist()
def get_document_block_data_v2(
	type_doc: str | None = None,
	q: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	status_filter: str | None = None,  # "", "Hoàn thành", "Đang xử lý", "Quá hạn"
	page: int | None = 1,
	page_size: int | None = 20,
):
	"""
	Trả dữ liệu cho Custom HTML Block:
	- rows: danh sách theo trang + computed_status
	- has_next: có trang tiếp theo không
	- kpis: { total, completed, processing, overdue } (tính trên toàn bộ tập lọc, KHÔNG theo status_filter)

	Chỉ tính 3 loại: Công văn đến / Công văn đi / Quyết định.
	"""
	page = max(1, cint(page or 1))
	page_size = max(1, cint(page_size or 20))

	type_doc = (type_doc or "").strip() or "Công văn đến"
	if type_doc not in _ALLOWED_BLOCK_TYPES:
		type_doc = "Công văn đến"

	q = (q or "").strip()
	status_filter = (status_filter or "").strip()

	# ===== Filters =====
	post_filter = None
	base_filters = [["docstatus", "<", 2]]

	# Quyết định lưu: type="Công văn đi" + type_doc="QĐ"
	if type_doc == "Quyết định":
		base_filters.append(["type", "=", "Công văn đi"])
		base_filters.append(["type_doc", "=", "QĐ"])
	else:
		base_filters.append(["type", "=", type_doc])

		# Khi chọn "Công văn đi" thì loại QĐ ra bằng post_filter
		# (tránh filter ["type_doc","!=","QĐ"] làm rớt luôn NULL)
		if type_doc == "Công văn đi":
			post_filter = lambda d: (d.get("type_doc") or "").strip().upper() != "QĐ"

	if from_date:
		base_filters.append(["document_date", ">=", from_date])
	if to_date:
		base_filters.append(["document_date", "<=", to_date])

	or_filters = None
	if q:
		or_filters = [
			["reference_number", "like", f"%{q}%"],
			["summary", "like", f"%{q}%"],
			["sender", "like", f"%{q}%"],
			["noi_nhan", "like", f"%{q}%"],
		]

	fields = [
		"name",
		"type",
		"type_doc",
		"docstatus",
		"reference_number",
		"summary",
		"document_date",
		"received_date",
		"sender",
		"noi_nhan",
		"department",
		"nguoi_chu_tri",
		"chairperson_status",
		"trang_thai_chuyen_vien_xu_ly",
		"deadline",
		"deadline_cv_xu_ly",
		"deadline_chu_tri2",
	]

	today = getdate(nowdate())
	DOCTYPE_NAME = "VNT Document Management"

	# ===== 1) KPI counts (không theo status_filter) =====
	kpis = {"total": 0, "completed": 0, "processing": 0, "overdue": 0}

	batch = 2000
	offset = 0
	while True:
		chunk = frappe.get_list(
			DOCTYPE_NAME,
			filters=base_filters,
			or_filters=or_filters,
			fields=[
				"type",
				"type_doc",
				"docstatus",
				"chairperson_status",
				"trang_thai_chuyen_vien_xu_ly",
				"deadline",
				"deadline_cv_xu_ly",
				"deadline_chu_tri2",
			],
			limit_start=offset,
			limit_page_length=batch,
			order_by=None,
			ignore_permissions=False,
		) or []

		if not chunk:
			break

		for d in chunk:
			if post_filter and not post_filter(d):
				continue

			kpis["total"] += 1
			st = _block_compute_status(d, today=today)

			if st == "Hoàn thành":
				kpis["completed"] += 1
			elif st == "Đang xử lý":
				kpis["processing"] += 1
			elif st == "Quá hạn":
				kpis["overdue"] += 1

		if len(chunk) < batch:
			break
		offset += batch

	# ===== 2) Rows theo trang + status_filter =====
	want_start = (page - 1) * page_size
	want_end = want_start + page_size + 1  # +1 để biết has_next

	order_by = "document_date desc"
	use_custom_sort = type_doc in ("Công văn đến", "Công văn đi", "Quyết định")
	if use_custom_sort:
		order_by = "name desc"

	def _parse_doc_name_key(name: str) -> tuple[int, int, str]:
		name = (name or "").strip()
		year = 0
		seq = 0

		if "-" in name:
			parts = name.rsplit("-", 2)
			if len(parts) == 3:
				mmyy = parts[1].strip()
				seq_str = parts[2].strip()
				yy = mmyy[-2:] if len(mmyy) >= 2 else ""
				if yy.isdigit():
					year = 2000 + cint(yy)
				if seq_str.isdigit():
					seq = cint(seq_str)
		elif "." in name:
			parts = name.split(".")
			if len(parts) >= 3:
				seq_str = parts[-2].strip()
				year_str = parts[-1].strip()
				if year_str.isdigit():
					year = cint(year_str)
				if seq_str.isdigit():
					seq = cint(seq_str)

		return (year, seq, name)

	if use_custom_sort:
		import heapq

		matched_total = 0
		top_rows = []
		db_offset = 0

		while True:
			chunk = frappe.get_list(
				DOCTYPE_NAME,
				filters=base_filters,
				or_filters=or_filters,
				fields=fields,
				limit_start=db_offset,
				limit_page_length=batch,
				order_by=order_by,
				ignore_permissions=False,
			) or []

			if not chunk:
				break

			for d in chunk:
				if post_filter and not post_filter(d):
					continue

				st = _block_compute_status(d, today=today)
				if status_filter and st != status_filter:
					continue

				matched_total += 1
				d["computed_status"] = st

				key = _parse_doc_name_key(d.get("name"))
				item = (key, d)
				if len(top_rows) < want_end:
					heapq.heappush(top_rows, item)
				else:
					if item > top_rows[0]:
						heapq.heapreplace(top_rows, item)

			if len(chunk) < batch:
				break
			db_offset += batch

		sorted_rows = [item[1] for item in sorted(top_rows, key=lambda x: x[0], reverse=True)]
		rows = sorted_rows[want_start:want_start + page_size]
		has_next = matched_total > want_start + page_size
	else:
		matched = []
		skipped = 0
		db_offset = 0

		while len(matched) < want_end:
			chunk = frappe.get_list(
				DOCTYPE_NAME,
				filters=base_filters,
				or_filters=or_filters,
				fields=fields,
				limit_start=db_offset,
				limit_page_length=batch,
				order_by=order_by,
				ignore_permissions=False,
			) or []

			if not chunk:
				break

			for d in chunk:
				if post_filter and not post_filter(d):
					continue

				st = _block_compute_status(d, today=today)
				if status_filter and st != status_filter:
					continue

				if skipped < want_start:
					skipped += 1
					continue

				d["computed_status"] = st
				matched.append(d)

				if len(matched) >= want_end:
					break

			if len(chunk) < batch:
				break
			db_offset += batch

		has_next = len(matched) > page_size
		rows = matched[:page_size]

	# ===== 3) Enrich rows for incoming: chair_department =====
	if type_doc == "Công văn đến" and rows:
		chair_ids = sorted({r.get("nguoi_chu_tri") for r in rows if r.get("nguoi_chu_tri")})
		chair_dept_map = {}
		if chair_ids:
			emps = frappe.get_all(
				"Employee",
				filters={"name": ["in", chair_ids]},
				fields=["name", "department"],
				ignore_permissions=True,
			) or []
			chair_dept_map = {e["name"]: e.get("department") for e in emps}

		for r in rows:
			emp = r.get("nguoi_chu_tri")
			r["chair_department"] = chair_dept_map.get(emp, "") if emp else ""

	return {
		"rows": rows,
		"has_next": has_next,
		"kpis": kpis,
		"type_doc": type_doc,
		"status_filter": status_filter or None,
	}

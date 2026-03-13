import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


MANAGER_GROUP = "Người quản lý"


class VNTLeaderWeeklyTrip(Document):
	def validate(self):
		# Use generated document ID (from naming series) as the visible title.
		self.display_title = self.name if self.name else ""
		self._validate_date_range()
		self._validate_people()

	def _validate_date_range(self):
		if not self.from_date or not self.to_date:
			return

		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("Từ ngày không được lớn hơn Đến ngày"))

	def _validate_people(self):
		rows = self.get("items") or []
		if not rows:
			frappe.throw(_("Vui lòng thêm ít nhất 1 người đi công tác"))

		emp_ids = []
		fd = getdate(self.from_date) if self.from_date else None
		td = getdate(self.to_date) if self.to_date else None

		for idx, row in enumerate(rows, start=1):
			emp = (row.get("employee") or "").strip()
			if not emp:
				frappe.throw(_("Dòng {0}: chưa chọn nhân sự").format(idx))

			trip_date = row.get("trip_date")
			if not trip_date:
				frappe.throw(_("Dòng {0}: chưa chọn ngày công tác").format(idx))

			slot = (row.get("time_slot") or "").strip()
			if slot not in {"Sáng", "Chiều", "Cả ngày"}:
				frappe.throw(_("Dòng {0}: buổi công tác không hợp lệ").format(idx))

			if not (row.get("destination") or "").strip():
				frappe.throw(_("Dòng {0}: chưa nhập nơi công tác").format(idx))

			if not (row.get("purpose") or "").strip():
				frappe.throw(_("Dòng {0}: chưa nhập nội dung đi").format(idx))

			if fd and td:
				trip_day = getdate(trip_date)
				if trip_day < fd or trip_day > td:
					frappe.throw(
						_("Dòng {0}: ngày công tác phải nằm trong khoảng từ ngày đến ngày của phiếu").format(idx)
					)

			emp_ids.append(emp)

		if not emp_ids:
			return

		emp_rows = frappe.get_all(
			"Employee",
			filters={"name": ["in", emp_ids]},
			fields=["name", "employee_name", "custom_designation_group"],
		)
		emp_map = {row["name"]: row for row in emp_rows}

		invalid = []
		for emp_id in emp_ids:
			employee = emp_map.get(emp_id) or {}
			if employee.get("custom_designation_group") != MANAGER_GROUP:
				invalid.append(employee.get("employee_name") or emp_id)

		if invalid:
			frappe.throw(
				_("Chỉ được chọn nhân sự có nhóm chức danh là '{0}'. Không hợp lệ: {1}").format(
					MANAGER_GROUP, ", ".join(invalid)
				)
			)

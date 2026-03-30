# Copyright (c) 2026, Vinatex and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document


class VNTEmployeeAuthorization(Document):
	"""
	DocType lưu thông tin ủy quyền nhân sự (Employee Authorization).

	Khi nhân sự A nghỉ phép và ủy quyền cho B:
	  - Các Role của A được sao chép sang B.
	  - Bản ghi này lưu: leave_application, employee_from, employee_to,
	    from_date, to_date, roles_granted (JSON), is_active.
	  - Khi hết hạn (to_date < hôm nay) hoặc bị thu hồi (is_active = 0),
	    các Role đã cấp sẽ được xóa khỏi User của B.
	"""
	pass

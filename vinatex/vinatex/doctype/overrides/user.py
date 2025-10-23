import frappe
from frappe.core.doctype.user.user import User

class CustomUser(User):
    def set_full_name(self):
        # middle_name là custom field bạn thêm (nếu có)
        self.full_name = " ".join(
            filter(
                None,
                [self.first_name, getattr(self, "middle_name", None), self.last_name],
            )
        )

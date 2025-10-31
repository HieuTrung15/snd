import re
import frappe
from frappe import _
from frappe.model.document import Document

class VNTNewFeed(Document):
    def before_save(self):
        # NEW thì để autoname xử lý; SUBMITTED thì không rename
        if self.is_new() or self.docstatus > 0:
            return

        raw = (self.title or "").strip()
        if not raw or raw == self.name:
            return

        # sanitize tên
        target = re.sub(r"[^\w\s.\-]", "-", raw)
        target = re.sub(r"\s+", " ", target).strip()[:140] or self.name
        if target == self.name:
            return

        if getattr(self.flags, "in_rename", False):
            return

        if frappe.db.exists(self.doctype, target):
            frappe.throw(_("Tên '{0}' đã tồn tại, vui lòng chỉnh 'Title'.").format(target))

        self.flags.in_rename = True
        try:
            # v15+: không có ignore_permissions; có thể có show_alert
            try:
                frappe.rename_doc(
                    doctype=self.doctype,
                    old=self.name,
                    new=target,
                    force=False,
                    merge=False,
                    show_alert=False,     # nếu môi trường bạn không có tham số này, khối except sẽ xử lý
                )
            except TypeError:
                # fallback cho môi trường không có show_alert
                frappe.rename_doc(
                    doctype=self.doctype,
                    old=self.name,
                    new=target,
                    force=False,
                    merge=False,
                )

            self.name = target
        finally:
            self.flags.in_rename = False

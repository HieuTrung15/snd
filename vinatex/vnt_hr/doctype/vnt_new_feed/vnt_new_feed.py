import re
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_url_to_form
from frappe.utils.data import escape_html

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


def _get_active_employee_users() -> list[str]:
    users = frappe.db.sql(
        """
        SELECT DISTINCT emp.user_id
        FROM `tabEmployee` AS emp
        INNER JOIN `tabUser` AS usr ON usr.name = emp.user_id
        WHERE emp.status = 'Active'
          AND IFNULL(emp.user_id, '') != ''
          AND IFNULL(usr.enabled, 0) = 1
        """,
        as_dict=False,
    )
    return sorted(
        {
            (row[0] or "").strip()
            for row in users
            if row and (row[0] or "").strip() and (row[0] or "").strip().lower() != "guest"
        }
    )


def _build_teams_message(doc: "VNTNewFeed") -> str:
    doc_url = get_url_to_form(doc.doctype, doc.name)
    return "<br>".join([
        "Thông báo quan trọng Tập đoàn.",
        escape_html(doc.title or doc.name),
        f'<a href="{escape_html(doc_url)}">Xem thông báo chi tiết</a>',
    ])


@frappe.whitelist()
def send_teams_notification(docname: str) -> dict:
    if not docname:
        frappe.throw(_("Chưa có tên cho bản tin."))

    doc = frappe.get_doc("VNT New Feed", docname)
    doc.check_permission("write")

    if cint(doc.da_gui_thong_bao):
        frappe.throw(_("Bản tin này đã gửi thông báo trước đó."))

    recipients = _get_active_employee_users()
    if not recipients:
        frappe.throw(_("Không tìm thấy nhân sự có tài khoản phù hợp để gửi thông báo."))
    total_active = frappe.db.count("Employee", {"status": "Active"}) or 0

    message = _build_teams_message(doc)

    frappe.enqueue(
        "vinatex.integrations.teams_graph.notify_user",
        queue="default",
        timeout=1800,
        is_async=True,
        upn_or_email=recipients,
        content_type="html",
        linkify=False,
        message=message,
        continue_on_error=True,
    )

    doc.db_set("da_gui_thong_bao", 1, update_modified=True)

    return {
        "ok": True,
        "active_total": total_active,
        "skipped_count": max(total_active - len(recipients), 0),
        "recipients_count": len(recipients),
        "docname": doc.name,
    }

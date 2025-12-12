import frappe
from frappe.utils import pretty_date, strip_html

@frappe.whitelist()
def get_my_todos(limit: int = 4):
    user = frappe.session.user
    if not user or user == "Guest":
        return []

    try:
        limit = int(limit or 4)
    except Exception:
        limit = 4

    filters = {"status": "Open"}
    if user != "Administrator":
        filters["allocated_to"] = user

    todos = frappe.get_list(
        "ToDo",
        filters=filters,
        fields=[
            "name",
            "description",
            "reference_type",
            "reference_name",
            "status",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=limit,
    )

    # nếu không còn todo đang mở thì trả về todo đã đóng
    if not todos:
        filters["status"] = "Closed"
        todos = frappe.get_list(
            "ToDo",
            filters=filters,
            fields=[
                "name",
                "description",
                "reference_type",
                "reference_name",
                "status",
                "modified",
            ],
            order_by="modified desc",
            limit_page_length=limit,
        )

    for t in todos:
        raw = t.get("description") or ""
        clean = strip_html(raw).strip()
        # vì FE đã clamp 2 dòng, bạn có thể nới chút để nhìn tự nhiên hơn
        if len(clean) > 220:
            clean = clean[:220] + "…"
        t["description"] = clean
        t["time_ago"] = pretty_date(t["modified"]) if t.get("modified") else ""

    return todos

@frappe.whitelist()
def get_vnt_news(limit: int = 4):
    try:
        limit = int(limit or 4)
    except Exception:
        limit = 4

    try:
        news_list = frappe.get_list(
            "VNT New Feed",
            fields=["name", "date"],
            order_by="`tabVNT New Feed`.`date` desc, `tabVNT New Feed`.`modified` desc",
            limit_page_length=limit,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "VNT News Feed get_vnt_news")
        raise

    return news_list

import frappe

@frappe.whitelist()
def get_unread_notification_count():
    user = frappe.session.user
    latest_limit = 20
    cache_key = f"vnt:notif_unread:{user}:latest_{latest_limit}"

    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return int(cached)

    latest_logs = frappe.get_all(
        "Notification Log",
        filters={"for_user": user},
        fields=["read"],
        order_by="modified desc",
        limit_page_length=latest_limit,
    )
    count = sum(1 for row in (latest_logs or []) if not int(row.get("read") or 0))

    # cache 15s (tuỳ bạn). 15s là hợp lý: vừa nhẹ DB vừa không “lụt” realtime vì UI đã optimistic + realtime event
    frappe.cache().set_value(cache_key, count, expires_in_sec=15)
    return count


@frappe.whitelist()
def invalidate_unread_notification_cache(user=None):
    # gọi khi có event mới/mark read để badge sync nhanh
    user = user or frappe.session.user
    frappe.cache().delete_value(f"vnt:notif_unread:{user}")
    frappe.cache().delete_value(f"vnt:notif_unread:{user}:latest_20")
    return True

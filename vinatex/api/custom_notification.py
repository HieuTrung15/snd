import frappe

@frappe.whitelist()
def get_unread_notification_count():
    user = frappe.session.user
    cache_key = f"vnt:notif_unread:{user}"

    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return int(cached)

    count = frappe.db.count("Notification Log", {
        "for_user": user,
        "read": 0
    })

    # cache 15s (tuỳ bạn). 15s là hợp lý: vừa nhẹ DB vừa không “lụt” realtime vì UI đã optimistic + realtime event
    frappe.cache().set_value(cache_key, count, expires_in_sec=15)
    return count


@frappe.whitelist()
def invalidate_unread_notification_cache(user=None):
    # gọi khi có event mới/mark read để badge sync nhanh
    user = user or frappe.session.user
    frappe.cache().delete_value(f"vnt:notif_unread:{user}")
    return True

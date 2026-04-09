import frappe


def close_todos_and_mark_notifications(todo_names):
	"""Close ToDos in batch and mark related notifications as read."""
	names = _unique_names(todo_names)
	if not names:
		return

	todos = frappe.get_all(
		"ToDo",
		filters={"name": ["in", names]},
		fields=["name", "status", "allocated_to", "reference_type", "reference_name"],
		limit_page_length=0,
	)
	if not todos:
		return

	closable_names = []
	notification_targets = set()

	for todo in todos:
		status = (todo.get("status") or "").strip().lower()
		if status not in {"closed", "cancelled"}:
			closable_names.append(todo.get("name"))

		user = (todo.get("allocated_to") or "").strip()
		reference_type = (todo.get("reference_type") or "").strip()
		reference_name = (todo.get("reference_name") or "").strip()
		if user and reference_type and reference_name:
			notification_targets.add((user, reference_type, reference_name))

	if closable_names:
		frappe.db.set_value(
			"ToDo",
			{"name": ["in", closable_names]},
			"status",
			"Closed",
			update_modified=False,
		)

	_mark_notifications_as_read(notification_targets)


def sync_notification_state_on_todo_update(doc, method=None):
	"""When a ToDo is closed via normal save flow, sync linked notifications."""
	if not doc or not doc.name:
		return

	if (doc.get("status") or "").strip().lower() != "closed":
		return

	try:
		if hasattr(doc, "has_value_changed") and not doc.has_value_changed("status"):
			return
	except Exception:
		pass

	close_todos_and_mark_notifications([doc.name])


def _mark_notifications_as_read(targets):
	users = set()
	for user, document_type, document_name in targets or []:
		frappe.db.set_value(
			"Notification Log",
			{
				"for_user": user,
				"document_type": document_type,
				"document_name": document_name,
				"read": 0,
			},
			"read",
			1,
			update_modified=False,
		)
		users.add(user)

	for user in users:
		frappe.cache().delete_value(f"vnt:notif_unread:{user}")
		frappe.publish_realtime("notification", user=user, after_commit=True)


def _unique_names(todo_names):
	unique = []
	seen = set()
	for name in todo_names or []:
		if not name or name in seen:
			continue
		seen.add(name)
		unique.append(name)
	return unique

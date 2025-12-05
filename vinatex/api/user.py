import frappe


@frappe.whitelist()
def get_current_user_gender():
    """
    Return gender of the logged-in user.

    Priority:
    1. Employee linked to the current user (user_id)
    2. Gender field on User (if available)
    """
    user = frappe.session.user

    if not user or user == "Guest":
        return {"gender": None}

    gender = frappe.db.get_value("Employee", {"user_id": user}, "gender")

    if not gender:
        gender = frappe.db.get_value("User", user, "gender")

    return {"gender": gender}

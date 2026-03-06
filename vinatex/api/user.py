import frappe


@frappe.whitelist()
def get_current_user_gender():
    """
    Return profile fields of the logged-in user.

    Priority:
    1. Employee linked to the current user (user_id)
    2. Gender field on User (if available, for gender only)
    """
    user = frappe.session.user

    if not user or user == "Guest":
        return {"gender": None, "designation": None, "department": None}

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user},
        ["gender", "designation", "department"],
        as_dict=True,
    ) or {}

    gender = employee.get("gender")
    if not gender:
        gender = frappe.db.get_value("User", user, "gender")

    return {
        "gender": gender,
        "designation": employee.get("designation"),
        "department": employee.get("department"),
    }

from __future__ import unicode_literals


import frappe
from erpnext.setup.doctype.employee.employee import (
    Employee
)



class VntEmployee(Employee):
    pass

@frappe.whitelist()
def get_approver_by_department(department):
    approver = frappe.get_value("Department Approver", {"parent": department}, "approver")
    if approver:
        return approver
    return None
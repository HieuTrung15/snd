import frappe
from frappe.utils import getdate, get_first_day, get_last_day

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Bộ phận", "fieldname": "department", "fieldtype": "Data", "width": 180},

        {"label": "Đầu kỳ - Tổng số", "fieldname": "begin_total", "fieldtype": "Int", "width": 100},
        {"label": "Đầu kỳ - Nữ", "fieldname": "begin_female", "fieldtype": "Int", "width": 100},

        {"label": "Tăng - Tổng số", "fieldname": "increase_total", "fieldtype": "Int", "width": 100},
        {"label": "Tăng - Nữ", "fieldname": "increase_female", "fieldtype": "Int", "width": 100},

        {"label": "Giảm - Tổng số", "fieldname": "decrease_total", "fieldtype": "Int", "width": 100},
        {"label": "Giảm - Nữ", "fieldname": "decrease_female", "fieldtype": "Int", "width": 100},

        {"label": "Giảm - Nghỉ hưu", "fieldname": "decrease_retire", "fieldtype": "Int", "width": 110},
        {"label": "Giảm - Chấm dứt HĐLĐ", "fieldname": "decrease_contract_end", "fieldtype": "Int", "width": 140},
        {"label": "Giảm - Điều động nội bộ", "fieldname": "decrease_internal", "fieldtype": "Int", "width": 140},
        {"label": "Giảm - Điều chuyển công tác", "fieldname": "decrease_transfer", "fieldtype": "Int", "width": 140},

        {"label": "Cuối kỳ - Tổng số", "fieldname": "end_total", "fieldtype": "Int", "width": 100},
        {"label": "Cuối kỳ - Nữ", "fieldname": "end_female", "fieldtype": "Int", "width": 100},

        {"label": "HĐLĐ - Không XĐ thời hạn", "fieldname": "contract_indef", "fieldtype": "Int", "width": 140},
        {"label": "HĐLĐ - Xác định thời hạn", "fieldname": "contract_def", "fieldtype": "Int", "width": 140},
        {"label": "HĐLĐ - Thử việc", "fieldname": "contract_probation", "fieldtype": "Int", "width": 100},
        {"label": "HĐLĐ - Không giao kết", "fieldname": "contract_none", "fieldtype": "Int", "width": 120},
        {"label": "HĐLĐ - Khác", "fieldname": "contract_other", "fieldtype": "Int", "width": 100},
    ]


def get_data(filters):
    from_date = getdate(filters.get("from_date")) if filters.get("from_date") else get_first_day(getdate())
    to_date = getdate(filters.get("to_date")) if filters.get("to_date") else get_last_day(getdate())

    departments = frappe.get_all("Department", filters={"company": filters.get("company")}, fields=["name"])
    data = []
    stt = 1

    for d in departments:
        dept_name = d.name

        # --- Demo cách đếm nhân sự, bạn sẽ phải thay bằng query thực tế ---
        begin_total = frappe.db.count("Employee", {
            "department": dept_name,
            "status": "Active",
            "date_of_joining": ("<", from_date)
        })
        begin_female = frappe.db.count("Employee", {
            "department": dept_name,
            "status": "Active",
            "date_of_joining": ("<", from_date),
            "gender": "Female"
        })

        increase_total = frappe.db.count("Employee", {
            "department": dept_name,
            "date_of_joining": ("between", [from_date, to_date])
        })
        increase_female = frappe.db.count("Employee", {
            "department": dept_name,
            "date_of_joining": ("between", [from_date, to_date]),
            "gender": "Female"
        })

        # Giả sử bạn có custom field "leaving_reason"
        decreases = frappe.db.get_all("Employee", 
            filters={
                "department": dept_name,
                "relieving_date": ("between", [from_date, to_date])
            },
            fields=["name", "gender"]
        )
        decrease_total = len(decreases)
        decrease_female = len([x for x in decreases if x.gender == "Female"])
        decrease_retire = len([x for x in decreases if x.leaving_reason == "Nghỉ hưu"])
        decrease_contract_end = len([x for x in decreases if x.leaving_reason == "Chấm dứt HĐLĐ"])
        decrease_internal = len([x for x in decreases if x.leaving_reason == "Điều động nội bộ"])
        decrease_transfer = len([x for x in decreases if x.leaving_reason == "Điều chuyển công tác"])

        end_total = begin_total + increase_total - decrease_total
        end_female = begin_female + increase_female - decrease_female

        # Demo phân loại hợp đồng (giả sử có field contract_type trong Employee)
        # contract_indef = frappe.db.count("Employee", {"department": dept_name, "contract_type": "Không xác định thời hạn"})
        # contract_def = frappe.db.count("Employee", {"department": dept_name, "contract_type": "Xác định thời hạn"})
        # contract_probation = frappe.db.count("Employee", {"department": dept_name, "contract_type": "Thử việc"})
        # contract_none = frappe.db.count("Employee", {"department": dept_name, "contract_type": "Không giao kết"})
        # contract_other = frappe.db.count("Employee", {"department": dept_name, "contract_type": "Khác"})

        data.append({
            "department": dept_name,
            "begin_total": begin_total,
            "begin_female": begin_female,
            "increase_total": increase_total,
            "increase_female": increase_female,
            "decrease_total": decrease_total,
            "decrease_female": decrease_female,
            "decrease_retire": decrease_retire,
            "decrease_contract_end": decrease_contract_end,
            "decrease_internal": decrease_internal,
            "decrease_transfer": decrease_transfer,
            "end_total": end_total,
            "end_female": end_female,
            # "contract_indef": contract_indef,
            # "contract_def": contract_def,
            # "contract_probation": contract_probation,
            # "contract_none": contract_none,
            # "contract_other": contract_other,
        })
        stt += 1

    return data

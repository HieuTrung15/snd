import frappe
from frappe.utils.data import getdate
from collections import defaultdict

def execute(filters=None):
    if not filters:
        filters = {}

    # Lấy ngày tham chiếu
    to_date = getdate(filters.get("to_date")) if filters.get("to_date") else getdate()

    # Nhóm tuổi
    age_groups = [
        ("<20", 0, 19),
        ("20-25", 20, 25),
        ("25-30", 25, 30),
        ("30-35", 30, 35),
        ("35-40", 35, 40),
        ("40-45", 40, 45),
        ("45-50", 45, 50),
        ("50-55", 50, 55),
        ("55-60", 55, 60),
        (">=60", 60, 200),
    ]

    # Định nghĩa cột báo cáo
    columns = [
        {"label": "STT", "fieldname": "stt", "fieldtype": "Int", "width": 50},
        {"label": "Đơn vị/Bộ phận", "fieldname": "department", "fieldtype": "Data", "width": 200},
    ]
    for label, *_ in age_groups:
        columns.append({"label": f"{label} (Nam)", "fieldname": f"{label.replace('>=','ge').replace('-','_')}_male", "fieldtype": "Int", "width": 80})
        columns.append({"label": f"{label} (Nữ)", "fieldname": f"{label.replace('>=','ge').replace('-','_')}_female", "fieldtype": "Int", "width": 80})

	# filters
    conditions = "status='Active' AND date_of_birth IS NOT NULL"
    params = {"to_date": to_date}

    if filters.get("department"):
        conditions += " AND department=%(department)s"
        params["department"] = filters.get("department")

    if filters.get("gender"):
        conditions += " AND gender=%(gender)s"
        params["gender"] = filters.get("gender")

    # Lấy dữ liệu nhân viên
    rows = frappe.db.sql(f"""
        SELECT department, gender, FLOOR(DATEDIFF(%(to_date)s, date_of_birth)/365) AS age
        FROM `tabEmployee`
        WHERE 	{conditions}
    """, params, as_dict=True)

    # Gom nhóm thống kê
    stats = defaultdict(lambda: defaultdict(int))
    for r in rows:
        dep = r.department or "Khác"
        age = r.age or 0
        gender = (r.gender or "Male").lower()
        for label, a1, a2 in age_groups:
            if a1 <= age <= a2:
                key = f"{label.replace('>=','ge').replace('-','_')}_{'male' if gender=='male' else 'female'}"
                stats[dep][key] += 1
                break

    # Convert ra list để hiển thị
    data = []
    idx = 1
    for dep, counts in stats.items():
        row = {"stt": idx, "department": dep}
        row.update(counts)
        data.append(row)
        idx += 1

    return columns, data

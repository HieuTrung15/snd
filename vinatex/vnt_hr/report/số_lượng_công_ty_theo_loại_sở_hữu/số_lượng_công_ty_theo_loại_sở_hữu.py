import frappe

# Thứ tự hiển thị cố định
ORDER = ["Chi nhánh", "100% vốn", "CTCP chi phối", "CTCP liên kết", "Đầu tư khác"]

def execute(filters=None):
    # Lấy số lượng theo custom_ownership_type
    sql = """
        SELECT custom_ownership_type AS bucket, COUNT(*) AS cnt
        FROM `tabCompany`
        GROUP BY custom_ownership_type
    """
    raw = frappe.db.sql(sql, as_dict=True)
    counts = {r.bucket: r.cnt for r in raw}

    # Ghép theo thứ tự mong muốn
    labels = ORDER
    values = [counts.get(b, 0) for b in labels]

    # Donut chart
    chart = {
        "data": {
            "labels": labels,
            "datasets": [{"values": values}],
        },
        "type": "donut",
    }

    # Bảng chi tiết
    rows = [{"ownership_type": b, "count": v} for b, v in zip(labels, values)]
    columns = [
        {"label": "Loại sở hữu", "fieldname": "ownership_type", "fieldtype": "Data", "width": 200},
        {"label": "Số lượng",    "fieldname": "count",          "fieldtype": "Int",  "width": 100},
    ]

    # Summary
    report_summary = [{"label": "Tổng", "value": sum(values), "indicator": "blue"}]

    return columns, rows, None, chart, report_summary

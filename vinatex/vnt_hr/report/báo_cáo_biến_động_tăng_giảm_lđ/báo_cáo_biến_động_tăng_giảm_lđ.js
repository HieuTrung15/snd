// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["BÁO CÁO BIẾN ĐỘNG TĂNG GIẢM LĐ"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": "Từ ngày",
            "fieldtype": "Date",
            "reqd": 1,
            "default": getMonthStartEnd().start
        },
        {
            "fieldname": "to_date",
            "label": "Đến ngày",
            "fieldtype": "Date",
            "reqd": 1,
            "default": getMonthStartEnd().end
        },
        {
            "fieldname": "change",
            "label": "Loại biến động",
            "fieldtype": "Select",
            "options": ["Tất cả", "Lao động tăng", "Lao động giảm"].join("\n"),
            "default": "Tất cả"
        }
    ]
};
// hàm lấy ngày đầu và cuối tháng của ngày hiện tại (hoặc ngày truyền vào)
function getMonthStartEnd(date = new Date()) {
    const year = date.getFullYear();
    const month = date.getMonth();
    const startDate = new Date(year, month, 1);
    const endDate = new Date(year, month + 1, 0);
    // format về chuỗi YYYY-MM-DD cho ERPNext filter (Date)
    const fmt = d => d.toISOString().slice(0, 10);
    return {
        start: fmt(startDate),
        end: fmt(endDate)
    };
}

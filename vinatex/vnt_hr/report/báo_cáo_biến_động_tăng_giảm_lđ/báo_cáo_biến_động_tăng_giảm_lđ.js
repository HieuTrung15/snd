// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["BÁO CÁO BIẾN ĐỘNG TĂNG GIẢM LĐ"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": "Từ ngày",
            "fieldtype": "Date",
            "reqd": 1,
            "on_change": function(query_report) {
                validate_dates(query_report);
            }
        },
        {
            "fieldname": "to_date",
            "label": "Đến ngày",
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.get_today(),
            "on_change": function(query_report) {
                validate_dates(query_report);
            }
        },
        {
            "fieldname": "change",
            "label": "Loại biến động",
            "fieldtype": "Select",
            // Lưu ý: các giá trị gửi về backend đúng như chuỗi hiển thị
            "options": ["Tất cả", "Lao động tăng", "Lao động giảm"].join("\n"),
            "default": "Tất cả"
        }
    ],

    "onload": function(report) {
        // bảo đảm to_date luôn có mặc định nếu user xóa tay
        if (!report.get_values().to_date) {
            report.set_filter_value("to_date", frappe.datetime.get_today());
        }
    }
};

function validate_dates(query_report) {
    const v = query_report.get_values();
    if (v.from_date && v.to_date) {
        const fromObj = frappe.datetime.str_to_obj(v.from_date);
        const toObj = frappe.datetime.str_to_obj(v.to_date);
        if (fromObj > toObj) {
            frappe.msgprint(__("“Từ ngày” không được lớn hơn “Đến ngày”"));
            query_report.set_filter_value("from_date", v.to_date);
        }
    }
}

// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Báo cáo các thay đổi về nhân sự"] = {
	"filters": [
        {
            fieldname: "from_date",
            label: "Từ ngày (hiệu lực)",
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
            on_change: function (r) { validate_dates(r); }
        },
        {
            fieldname: "to_date",
            label: "Đến ngày (hiệu lực)",
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
            on_change: function (r) { validate_dates(r); }
        },
        {
            fieldname: "decision_type",
            label: "Loại quyết định",
            fieldtype: "Link",
            options: "VNT Decision Type"   // hoặc Select nếu muốn danh sách tĩnh
        },
        {
            fieldname: "department",
            label: "Phòng ban (NV)",
            fieldtype: "Link",
            options: "Department"
        },
        {
            fieldname: "company",
            label: "Công ty (NV)",
            fieldtype: "Link",
            options: "Company"
        },
        {
            fieldname: "only_approved",
            label: "Chỉ lấy đã phê duyệt",
            fieldtype: "Check",
            default: 1
        },
        {
            fieldname: "search",
            label: "Tìm theo Mã/Tên",
            fieldtype: "Data"
        }
    ]
};

function validate_dates(query_report) {
    const v = query_report.get_values();
    if (v.from_date && v.to_date) {
        const f = frappe.datetime.str_to_obj(v.from_date);
        const t = frappe.datetime.str_to_obj(v.to_date);
        if (f > t) {
            frappe.msgprint(__("“Từ ngày” không được lớn hơn “Đến ngày”. Hệ thống sẽ đặt “Từ ngày” = “Đến ngày”."));
            query_report.set_filter_value("from_date", v.to_date);
        }
    }
}
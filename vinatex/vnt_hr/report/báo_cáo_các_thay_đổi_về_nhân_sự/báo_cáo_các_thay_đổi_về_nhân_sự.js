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
        },
        {
            fieldname: "to_date",
            label: "Đến ngày (hiệu lực)",
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "decision_type",
            label: "Loại quyết định",
            fieldtype: "Link",
            options: "VNT Decision Type"   
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
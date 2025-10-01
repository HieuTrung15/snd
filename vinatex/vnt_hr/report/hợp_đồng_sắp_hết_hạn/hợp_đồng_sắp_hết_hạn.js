// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Hợp đồng sắp hết hạn"] = {
	 "filters": [
        {
            fieldname: "from_date",
            label: __("Từ ngày"),
            fieldtype: "Date",
            default: frappe.datetime.get_today()
        },
        {
            fieldname: "to_date",
            label: __("Đến ngày"),
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), 30)
        },
        {
            fieldname: "department",
            label: __("Phòng ban"),
            fieldtype: "Link",
            options: "Department"
        },
        {
            fieldname: "employee",
            label: __("Nhân viên"),
            fieldtype: "Link",
            options: "Employee"
        },
        {
            fieldname: "status",
            label: __("Trạng thái NV"),
            fieldtype: "Select",
            options: "\nActive\nLeft\nSuspended\nOn Leave",
            default: "Active"
        }
    ]
};

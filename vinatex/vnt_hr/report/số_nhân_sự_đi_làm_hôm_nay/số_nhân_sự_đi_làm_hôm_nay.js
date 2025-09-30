// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số nhân sự đi làm hôm nay"] = {
	"filters": [
		 {
            fieldname: "Date",
            label: __("Ngày"),
            fieldtype: "Date",
            default: frappe.datetime.get_today()
        },
        {
            fieldname: "employee",
            label: __("Mã/Tên nhân sự"),
            fieldtype: "Link",
            options: "Employee",
            reqd: 0
        },
        {
            fieldname: "department",
            label: __("Phòng ban"),
            fieldtype: "Link",
            options: "Department",
            reqd: 0
        }
	]
};

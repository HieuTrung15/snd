// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số nhân sự đi làm hôm nay"] = {
	"filters": [
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
        },
        {
            fieldname: "branch",
            label: __("Chi nhánh"),
            fieldtype: "Link",
            options: "Branch",
            reqd: 0
        },
        {
            fieldname: "employee",
            label: __("Nhân viên"),
            fieldtype: "Link",
            options: "Employee",
            hidden: 1,
            default: frappe.session.user
        }
	]
};

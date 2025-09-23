// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh sách nhân viên đi công tác trong tháng"] = {
	filters: [
    {
      fieldname: "month",
      label: __("Tháng"),
      fieldtype: "Select",
      options: [
        "1","2","3","4","5","6","7","8","9","10","11","12"
      ],
      default: (new Date().getMonth() + 1).toString(),
      reqd: 1
    },
    {
      fieldname: "year",
      label: __("Năm"),
      fieldtype: "Int",
      default: new Date().getFullYear(),
      reqd: 1
    },
    {
      fieldname: "company",
      label: __("Công ty"),
      fieldtype: "Link",
      options: "Company"
    },
    {
      fieldname: "department",
      label: __("Phòng ban"),
      fieldtype: "Link",
      options: "Department"
    }
  ]
};

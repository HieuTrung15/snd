// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số ngày phép còn lại"] = {
	filters: [
    {fieldname: "leave_type", label: "Leave Type", fieldtype: "Data", default: "Nghỉ phép năm", reqd: 1}
  ]
};

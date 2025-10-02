// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Thâm niên làm việc"] = {
	 "filters": [
    { fieldname: "as_of_date", label: __("Tính đến ngày"), fieldtype: "Date", default: frappe.datetime.get_today() },
    { fieldname: "company", label: __("Công ty"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
    { fieldname: "department", label: __("Phòng/Ban"), fieldtype: "Link", options: "Department",
      get_query() {
        const company = frappe.query_report.get_filter_value("company");
        return company ? { filters: { company } } : {};
      }
    }
  ]
};

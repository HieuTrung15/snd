// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh sách chấm công theo tháng"] = {
  onload: function(report) {
    // Set mặc định: đầu tháng → cuối tháng hiện tại
    const start = frappe.datetime.month_start();
    const end = frappe.datetime.month_end();
    report.set_filter_value('from_date', start);
    report.set_filter_value('to_date', end);

    if (!report.get_values().employee) {
      frappe.call({
        method: "vinatex.vnt_hr.report.attendance_month_common.get_employee_for_user",
        callback: function (r) {
          if (r && r.message && r.message.employee) {
            report.set_filter_value("employee", r.message.employee);
          }
        },
      });
    }
  },
  filters: [
    {fieldname: "from_date", label: __("From Date"), fieldtype: "Date"},
    {fieldname: "to_date", label: __("To Date"), fieldtype: "Date"},
    {fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee"},
    {fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department"},
    {fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company"}
  ]
};

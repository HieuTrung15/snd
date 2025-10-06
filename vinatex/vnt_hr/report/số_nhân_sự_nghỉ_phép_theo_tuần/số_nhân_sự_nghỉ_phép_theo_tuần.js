frappe.query_reports["Số nhân sự nghỉ phép theo tuần"] = {
  "filters": [
    {
      fieldname: "from_date",
      label: __("From Date"),
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.week_start()
    },
    {
      fieldname: "to_date",
      label: __("To Date"),
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.week_end()
    },
    {
      fieldname: "company",
      label: __("Company"),
      fieldtype: "Link",
      options: "Company",
      reqd: 0
    },
    {
      fieldname: "department",
      label: __("Department"),
      fieldtype: "Link",
      options: "Department",
      reqd: 0
    }
  ],
  onload: function(report) {
    // có thể tuỳ biến thêm tại đây nếu cần
  }
};

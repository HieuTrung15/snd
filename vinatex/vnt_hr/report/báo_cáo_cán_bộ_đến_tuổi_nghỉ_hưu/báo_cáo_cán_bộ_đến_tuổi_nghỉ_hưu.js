// Copyright (c) 2025, vinatex
// For license information, please see license.txt

frappe.query_reports["Báo cáo cán bộ đến tuổi nghỉ hưu"] = {
  "filters": [
    {
      fieldname: "from_date",
      label: "Từ ngày",
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.get_today()
    },
    {
      fieldname: "to_date",
      label: "Đến ngày",
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.add_days(frappe.datetime.get_today(),365)
    },
    {
      fieldname: "company",
      label: "Công ty",
      fieldtype: "Link",
      options: "Company"
    },
    {
      fieldname: "department",
      label: "Phòng ban",
      fieldtype: "Link",
      options: "Department"
    },
    {
      fieldname: "gender",
      label: "Giới tính",
      fieldtype: "Select",
      options: ["Tất cả", "Nam", "Nữ", "Male", "Female"].join("\n"),
      default: "Tất cả"
    }
  ],

  onload(report) {
    const v = report.get_values();
    if (!v.from_date) report.set_filter_value("from_date", frappe.datetime.get_today());
    if (!v.to_date)   report.set_filter_value("to_date", frappe.datetime.add_months(frappe.datetime.get_today(), 6));
  },

  // highlight số ngày còn lại
  formatter(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (column.fieldname === "days_until" && data) {
      const n = cint(data.days_until);
      if (n <= 0) value = `<span style="color:#d32f2f;font-weight:600">${value}</span>`;
      else if (n <= 90) value = `<span style="color:#f57c00;font-weight:600">${value}</span>`;
    }
    return value;
  }
};

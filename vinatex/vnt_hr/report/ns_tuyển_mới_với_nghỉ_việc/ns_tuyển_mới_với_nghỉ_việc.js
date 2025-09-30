// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["NS tuyển mới với nghỉ việc"] = {
	"filters": [
		{
      fieldname: "from_date",
      label: "Từ ngày",
      fieldtype: "Date",
      default: (() => {
        const today = frappe.datetime.get_today();
        // 12 tháng gần nhất (tính cả tháng hiện tại)
        const start = frappe.datetime.add_months(frappe.datetime.month_start(today), -11);
        return start;
      })()
    },
    {
      fieldname: "to_date",
      label: "Đến ngày",
      fieldtype: "Date",
      default: frappe.datetime.month_end(frappe.datetime.get_today())
    },
    {
      fieldname: "company",
      label: "Công ty",
      fieldtype: "Link",
      options: "Company",
      default: frappe.defaults.get_default("company")
    },
    {
      fieldname: "department",
      label: "Phòng/Ban",
      fieldtype: "Link",
      options: "Department"
    }
	],
	onload: function(report) {
    // Nhấn Run khi mở, để lấy chart ngay
    if (!report.get_values()) {
      report.refresh();
    }
  },

  // Optional: format số phải rõ ràng
  formatter: function(value, row, column) {
    if (["hiring_count", "attrition_count"].includes(column.fieldname) && value != null) {
      return `<span style="text-align:right; display:inline-block; width:100%;">${frappe.format(value, {fieldtype: "Int"})}</span>`;
    }
    return value;
  }
};

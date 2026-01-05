// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số ngày chấm công bất thường"] = {
  filters: [
    {
      fieldname: "employee",
      label: "Nhân viên",
      fieldtype: "Link",
      options: "Employee",
      reqd: 0,
    },
    {
      fieldname: "company",
      label: "Công ty",
      fieldtype: "Link",
      options: "Company",
    },
    {
      fieldname: "month",
      label: "Tháng",
      fieldtype: "Select",
      options: "\n01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
      reqd: 0,
      default: moment().format("MM"),
      on_change: set_range_from_month_year,
    },
    {
      fieldname: "year",
      label: "Năm",
      fieldtype: "Int",
      reqd: 0,
      default: moment().format("YYYY"),
      on_change: set_range_from_month_year,
    },
    {
      fieldname: "from_date",
      label: "Từ ngày",
      fieldtype: "Date",
      hidden: 1,
      reqd: 1,
    },
    {
      fieldname: "to_date",
      label: "Đến ngày",
      fieldtype: "Date",
      hidden: 1,
      reqd: 1,
    },
    {
      fieldname: "to_today",
      label: "Chỉ đến hôm nay",
      fieldtype: "Check",
      default: 1,
    },
  ],

  onload(report) {
    const defaults = frappe.defaults;
    const default_company =
      defaults.get_user_default("Company") ||
      defaults.get_global_default("company");

    if (default_company && !report.get_values().company) {
      report.set_filter_value("company", default_company);
    }

    if (!report.get_values().employee) {
      frappe.call({
        method: "frappe.client.get_value",
        args: {
          doctype: "Employee",
          filters: {
            user_id: frappe.session.user,
            status: "Active",
          },
          fieldname: "name",
        },
        callback(res) {
          const employee = res.message?.name;
          if (employee) {
            report.set_filter_value("employee", employee);
          }
        },
      });
    }

    set_range_from_month_year(report);
  },

  formatter(value, row, column, data, default_formatter) {
    const formatted = default_formatter(value, row, column, data);
    const fieldname = column.fieldname || "";
    const day = parseInt(fieldname.replace("d", ""), 10);

    if (Number.isInteger(day) && day >= 1 && day <= 31) {
      const codes = String(data?.[fieldname] || "")
        .split("/")
        .map((c) => c.trim())
        .filter(Boolean);
      const priority = ["BT", "BT(0.5)", "T"];
      const colorKey =
        codes.find((c) => priority.includes(c)) ||
        codes.find((c) => STATUS_COLORS[c]) ||
        (codes.length && codes[0]);
      const color = colorKey ? STATUS_COLORS[colorKey] : undefined;
      if (color) {
        return `<span style="background:${color}; padding:2px 6px; border-radius:4px; display:inline-block;">${value}</span>`;
      }
    }

    return formatted;
  },
};

const STATUS_COLORS = {
  BT: "rgba(255, 76, 76, .2)",
  "BT(0.5)": "rgba(255, 138, 101, .2)",
  T: "rgba(121, 85, 72, .15)",
};

function set_range_from_month_year(report) {
  const r = report || frappe.query_report;
  const { month, year } = r.get_values();
  const m = parseInt(month, 10);
  const y = parseInt(year, 10);

  if (!Number.isInteger(m) || !Number.isInteger(y)) return;

  const start = moment({ year: y, month: m - 1, day: 1 });
  const end = start.clone().endOf("month");

  r.set_filter_value("from_date", start.format("YYYY-MM-DD"));
  r.set_filter_value("to_date", end.format("YYYY-MM-DD"));
}

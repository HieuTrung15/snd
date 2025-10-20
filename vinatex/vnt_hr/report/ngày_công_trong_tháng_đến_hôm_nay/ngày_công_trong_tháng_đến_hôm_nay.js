// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Ngày công trong tháng đến hôm nay"] = {
  filters: [
    {
      fieldname: "employee",
      label: "Nhân viên",
      fieldtype: "Link",
      options: "Employee",
      reqd: 1,
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
      reqd: 1,
      default: moment().format("MM"),
      on_change: set_range_from_month_year,
    },
    {
      fieldname: "year",
      label: "Năm",
      fieldtype: "Int",
      reqd: 1,
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
      fieldname: "count_wfh",
      label: "Coi làm việc từ xa là đi làm",
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

    setTimeout(() => set_range_from_month_year(report), 0);
  },

  formatter(value, row, column, data, default_formatter) {
    const formatted = default_formatter(value, row, column, data);
    const fieldname = column.fieldname || "";
    const day = parseInt(fieldname.replace("d", ""), 10);

    if (Number.isInteger(day) && day >= 1 && day <= 31) {
      const code = String(data?.[fieldname] || "").toUpperCase();
      const color = STATUS_COLORS[code];
      if (color) {
        return `<span style="background:${color}; padding:2px 6px; border-radius:4px; display:inline-block;">${value}</span>`;
      }
    }

    return formatted;
  },
};

const STATUS_COLORS = {
  // X: "rgba(76, 175, 80, .12)", // Đi làm
  // P: "rgba(33, 150, 243, .12)", // Nghỉ phép
  // L: "rgba(158, 158, 158, .15)", // Nghỉ lễ
  T: "rgba(96, 125, 139, .12)", // Cuối tuần
  // V: "rgba(255, 76, 76, .15)", // Vắng mặt
  // O: "rgba(255, 193, 7, .2)", // Quên chấm công
  // CT: "rgba(156, 39, 176, .12)", // Công tác
  // Ro: "rgba(244, 67, 54, .12)", // Nghỉ không lương
  // "CĐ": "rgba(0, 188, 212, .12)", // Nghỉ hưởng lương
  // BH: "rgba(63, 81, 181, .12)", // Nghỉ BHXH
  // "N1/2": "rgba(255, 152, 0, .18)", // Nghỉ nửa ngày
  // CV: "rgba(121, 85, 72, .12)", // Chưa vào làm
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

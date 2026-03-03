frappe.query_reports["Tổng hợp chấm công tháng"] = {
  filters: [
    {
      fieldname: "company",
      label: "Công ty",
      fieldtype: "Link",
      options: "Company",
      reqd: 1,
      on_change: function () {
        update_workday_target_filter(frappe.query_report);
      },
    },
    {
      fieldname: "department",
      label: "Phòng ban",
      fieldtype: "Link",
      options: "Department",
    },
    {
      fieldname: "branch",
      label: "Văn phòng",
      fieldtype: "Link",
      options: "Branch",
    },
    {
      fieldname: "employee",
      label: "Nhân viên",
      fieldtype: "Link",
      options: "Employee",
      default: frappe.defaults.get_user_default("Employee"),
      on_change: function () {
        update_workday_target_filter(frappe.query_report);
      },
    },
    {
      fieldname: "workday_target_to_date",
      label: "Công chuẩn tháng",
      fieldtype: "Data",
      read_only: 1,
    },
    {
      fieldname: "month",
      label: "Tháng",
      fieldtype: "Select",
      options: "\n01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
      reqd: 1,
      on_change: function () {
        set_month_year_range_and_refresh(frappe.query_report);
      },
    },
    {
      fieldname: "year",
      label: "Năm",
      fieldtype: "Int",
      reqd: 1,
      on_change: function () {
        set_month_year_range_and_refresh(frappe.query_report);
      },
    },
    {
      fieldname: "show_detail_report",
      label: "Hiển thị dữ liệu máy chấm công",
      fieldtype: "Check",
      default: 0,
      on_change: function () {
        const r = frappe.query_report;
        if (r) {
          r.refresh();
        }
      },
    },
    {
      fieldname: "open_abnormal_attendance",
      label: "Chấm công bất thường",
      fieldtype: "Button",
      btn_size: "xs",
      click: function () {
        const vals = frappe.query_report.get_values() || {};
        frappe.route_options = {};
        if (vals.department) frappe.route_options.department = vals.department;
        if (vals.employee) frappe.route_options.employee = vals.employee;
        if (vals.month) frappe.route_options.month = vals.month;
        if (vals.year) frappe.route_options.year = vals.year;
        frappe.set_route("List", "VNT Attendance Confirm");
      },
    },
    {
      fieldname: "from_date",
      label: "Từ ngày",
      fieldtype: "Date",
      reqd: 1,
      hidden: 1,
    },
    {
      fieldname: "to_date",
      label: "Đến ngày",
      fieldtype: "Date",
      reqd: 1,
      hidden: 1,
    },
  ],

  onload: function (report) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");

    if (!report.get_values().year) {
      report.set_filter_value("year", yyyy);
    }
    if (!report.get_values().month) {
      report.set_filter_value("month", mm);
    }

    const vals = report.get_values();
    const y = parseInt(vals.year || yyyy, 10);
    const m = parseInt(vals.month || mm, 10);
    if (!isNaN(y) && !isNaN(m)) {
      const first = new Date(y, m - 1, 1);
      const last = new Date(y, m, 0);
      if (!vals.from_date) {
        report.set_filter_value("from_date", frappe.datetime.obj_to_str(first));
      }
      if (!vals.to_date) {
        report.set_filter_value("to_date", frappe.datetime.obj_to_str(last));
      }
    }

    const default_company =
      frappe.defaults.get_user_default("Company") ||
      frappe.defaults.get_global_default("company");
    if (default_company && !report.get_values().company) {
      report.set_filter_value("company", default_company);
    }

    if (!report.get_values().employee) {
      frappe.call({
        method: "vinatex.vnt_hr.report.attendance_month_common.get_employee_for_user",
        callback: function (r) {
          if (r && r.message && r.message.employee) {
            report.set_filter_value("employee", r.message.employee);
            update_workday_target_filter(report);
          }
        },
      });
    } else {
      update_workday_target_filter(report);
    }
  },

  formatter: function (value, row, column, data, default_formatter) {
    const formatted = default_formatter(value, row, column, data);
    const fieldname = column.fieldname || "";
    const day = parseInt(fieldname.replace("d", ""), 10);

    if (!Number.isInteger(day) || day < 1 || day > 31) {
      return formatted;
    }

    const dayMoment = get_day_moment_for_column(fieldname);
    if (!dayMoment) {
      return formatted;
    }

    const todayCutoff = moment().startOf("day").subtract(1, "day");
    const raw = String(data?.[fieldname] || "").trim();
    if (!raw && dayMoment.isSameOrBefore(todayCutoff, "day")) {
      return "<span style='display:block; background:#fde2e2; border-radius:4px; min-height:18px;'>&nbsp;</span>";
    }

    return formatted;
  },
};

function set_month_year_range_and_refresh(report) {
  const r = report || frappe.query_report;
  const vals = r.get_values() || {};
  const y = parseInt(vals.year, 10);
  const m = parseInt(vals.month, 10);
  if (isNaN(y) || isNaN(m)) return;

  const first = new Date(y, m - 1, 1);
  const last = new Date(y, m, 0);
  r.set_filter_value("from_date", frappe.datetime.obj_to_str(first));
  r.set_filter_value("to_date", frappe.datetime.obj_to_str(last));
  update_workday_target_filter(r);
  r.refresh();
}

function get_day_moment_for_column(fieldname) {
  const day = parseInt(String(fieldname || "").replace("d", ""), 10);
  if (!Number.isInteger(day) || day < 1 || day > 31) {
    return null;
  }

  const fromDate = frappe.query_report.get_filter_value("from_date");
  if (!fromDate) {
    return null;
  }

  const base = moment(fromDate, "YYYY-MM-DD");
  if (!base.isValid()) {
    return null;
  }

  const dayMoment = base.clone().date(day);
  if (dayMoment.month() !== base.month()) {
    return null;
  }

  return dayMoment;
}

function update_workday_target_filter(report) {
  const r = report || frappe.query_report;
  if (!r) return;
  const vals = r.get_values ? (r.get_values() || {}) : {};

  if (!vals.employee || !vals.from_date || !vals.to_date) {
    r.set_filter_value("workday_target_to_date", "");
    return;
  }

  frappe.call({
    method: "vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.tổng_hợp_chấm_công_tháng.get_workday_target_to_date",
    args: {
      employee: vals.employee,
      from_date: vals.from_date,
      to_date: vals.to_date,
      company: vals.company,
    },
    callback: function (res) {
      r.set_filter_value("workday_target_to_date", res?.message?.value || "");
    },
  });
}

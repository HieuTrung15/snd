function isDayColumn(fieldname) {
  return /^d\d{2}$/.test(fieldname || "");
}

function isEmptyCellValue(value) {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

frappe.query_reports["Tổng hợp chấm công tháng"] = {
  "filters": [
    {
      "fieldname": "company",
      "label": "Công ty",
      "fieldtype": "Link",
      "options": "Company",
      "reqd": 1
    },
    {
      "fieldname": "department",
      "label": "Phòng ban",
      "fieldtype": "Link",
      "options": "Department"
    },
    {
      "fieldname": "branch",
      "label": "Văn phòng",
      "fieldtype": "Link",
      "options": "Branch"
    },
    {
      "fieldname": "employee",
      "label": "Nhân viên",
      "fieldtype": "Link",
      "options": "Employee",
      "default": frappe.defaults.get_user_default("Employee")
    },
    
    {
      "fieldname": "month",
      "label": "Tháng",
      "fieldtype": "Select",
      "options": "\n01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
      "reqd": 1,
      on_change: function () {
        const r = frappe.query_report;
        const vals = r.get_values();
        const y = parseInt(vals.year, 10);
        const m = parseInt(vals.month, 10);
        if (!isNaN(y) && !isNaN(m)) {
          const first = new Date(y, m - 1, 1);
          const last = new Date(y, m, 0);
          r.set_filter_value("from_date", frappe.datetime.obj_to_str(first));
          r.set_filter_value("to_date", frappe.datetime.obj_to_str(last));
          r.refresh();
        }
      }
    },
    {
      "fieldname": "year",
      "label": "Năm",
      "fieldtype": "Int",
      "reqd": 1,
      on_change: function () {
        const r = frappe.query_report;
        const vals = r.get_values();
        const y = parseInt(vals.year, 10);
        const m = parseInt(vals.month, 10);
        if (!isNaN(y) && !isNaN(m)) {
          const first = new Date(y, m - 1, 1);
          const last = new Date(y, m, 0);
          r.set_filter_value("from_date", frappe.datetime.obj_to_str(first));
          r.set_filter_value("to_date", frappe.datetime.obj_to_str(last));
          r.refresh();
        }
      }
    },
    {
      "fieldname": "show_detail_report",
      "label": "Hiển thị dữ liệu máy chấm công",
      "fieldtype": "Check",
      "default": 0,
      on_change: function () {
        const r = frappe.query_report;
        if (r) {
          r.refresh();
        }
      }
    },
    {
      "fieldname": "open_abnormal_attendance",
      "label": "Chấm công bất thường",
      "fieldtype": "Button",
      "btn_size": "xs",
      click: function () {
        const vals = frappe.query_report.get_values() || {};
        frappe.route_options = {};
        if (vals.department) frappe.route_options.department = vals.department;
        if (vals.employee) frappe.route_options.employee = vals.employee;
        if (vals.month) frappe.route_options.month = vals.month;
        if (vals.year) frappe.route_options.year = vals.year;
        frappe.set_route("List", "VNT Attendance Confirm");
      }
    },
    {
      "fieldname": "from_date",
      "label": "Từ ngày",
      "fieldtype": "Date",
      "reqd": 1,
      "hidden": 1
    },
    {
      "fieldname": "to_date",
      "label": "Đến ngày",
      "fieldtype": "Date",
      "reqd": 1,
      "hidden": 1
    },
  ],

  formatter: function (value, row, column, data, default_formatter) {
    const formatted = default_formatter ? default_formatter(value, row, column, data) : value;
    const fieldname = column && column.fieldname ? column.fieldname : "";

    if (
      isDayColumn(fieldname) &&
      isEmptyCellValue(value)
    ) {
      return '<span style="display:block; width:100%; min-height:18px; background:#ffd6d6;">&nbsp;</span>';
    }

    return formatted;
  },

  onload: function (report) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0"); // "01".."12"

    // Set mặc định tháng/năm
    if (!report.get_values().year) {
      report.set_filter_value("year", yyyy);
    }
    if (!report.get_values().month) {
      report.set_filter_value("month", mm);
    }

    // Set mặc định nhân viên theo user đang login
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

    // Tính ngày đầu & cuối tháng theo tháng/năm đã chọn
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

    // Set mặc định Công ty
    const default_company =
      frappe.defaults.get_user_default("Company") ||
      frappe.defaults.get_global_default("company");

    if (default_company && !report.get_values().company) {
      report.set_filter_value("company", default_company);
    }

    // Hiển thị ghi chú ký hiệu một lần trên đầu báo cáo
  },
};

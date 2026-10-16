function isDayColumn(fieldname) {
  return /^d\d{2}$/.test(fieldname || "");
}

function isEmptyCellValue(value) {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

function installAttendanceLegendStyles() {
  let style = document.getElementById("vnt-attendance-legend-styles");
  if (!style) {
    style = document.createElement("style");
    style.id = "vnt-attendance-legend-styles";
    document.head.appendChild(style);
  }
  style.textContent = `
    .vnt-attendance-legend {
      display: block;
      width: 100%;
      color: var(--text-color);
      font-size: 13px;
    }
    .vnt-attendance-legend__summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 42px;
      padding: 2px 0 7px;
      color: var(--heading-color);
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      list-style: none;
      user-select: none;
    }
    .vnt-attendance-legend__summary::-webkit-details-marker { display: none; }
    .vnt-attendance-legend__summary::marker { display: none; content: ""; }
    .vnt-attendance-legend__summary::after {
      content: "⌃";
      display: inline-flex;
      flex: 0 0 34px;
      width: 34px;
      height: 34px;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--border-color);
      border-radius: 9px;
      background: var(--card-bg);
      color: var(--text-color);
      font-size: 20px;
      font-weight: 500;
      line-height: 1;
      transition: background-color .16s ease, transform .2s ease;
    }
    .vnt-attendance-legend__summary:hover::after {
      background: var(--subtle-fg);
    }
    .vnt-attendance-legend:not([open]) .vnt-attendance-legend__summary::after {
      transform: rotate(180deg);
    }
    .vnt-attendance-legend__grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(210px, 1fr));
      gap: 10px;
      padding-bottom: 8px;
    }
    .vnt-attendance-legend__group {
      --legend-color: #64748b;
      --legend-soft: #f8fafc;
      --legend-border: #dbe3ec;
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--border-color);
      border-radius: 10px;
      background: var(--card-bg);
      box-shadow: 0 2px 8px rgba(15, 23, 42, .035);
    }
    .vnt-attendance-legend__group.is-work {
      --legend-color: #2563eb;
      --legend-soft: #eff6ff;
      --legend-border: #bfdbfe;
    }
    .vnt-attendance-legend__group.is-leave {
      --legend-color: #059669;
      --legend-soft: #ecfdf5;
      --legend-border: #a7f3d0;
    }
    .vnt-attendance-legend__group.is-rest {
      --legend-color: #7c3aed;
      --legend-soft: #f5f3ff;
      --legend-border: #ddd6fe;
    }
    .vnt-attendance-legend__group.is-other {
      --legend-color: #64748b;
      --legend-soft: #f8fafc;
      --legend-border: #dbe3ec;
    }
    .vnt-attendance-legend__group.is-review {
      --legend-color: #0f766e;
      --legend-soft: #f0fdfa;
      --legend-border: #99f6e4;
    }
    .vnt-attendance-legend__group-title {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 9px;
      color: var(--legend-color);
      font-size: 13px;
      font-weight: 700;
      line-height: 1.35;
    }
    .vnt-attendance-legend__dot {
      flex: 0 0 10px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--legend-color);
      box-shadow: 0 0 0 3px var(--legend-soft);
    }
    .vnt-attendance-legend__item {
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      align-items: center;
      gap: 9px;
      min-height: 30px;
    }
    .vnt-attendance-legend__item + .vnt-attendance-legend__item { margin-top: 4px; }
    .vnt-attendance-legend__code {
      display: inline-flex;
      min-height: 24px;
      align-items: center;
      justify-content: center;
      padding: 2px 8px;
      border: 1px solid var(--legend-border);
      border-radius: 7px;
      background: var(--legend-soft);
      color: var(--legend-color);
      font-size: 12px;
      font-weight: 700;
      line-height: 1.2;
      white-space: nowrap;
    }
    .vnt-attendance-legend__description {
      min-width: 0;
      color: var(--text-color);
      font-size: 12px;
      line-height: 1.3;
    }
    .vnt-attendance-legend__note {
      margin-bottom: 2px;
      padding: 7px 10px;
      border-radius: 8px;
      background: var(--subtle-fg);
      color: var(--text-muted);
      font-size: 11px;
      line-height: 1.35;
    }
    .vnt-attendance-cell-link {
      display: block;
      color: inherit !important;
      text-decoration: none !important;
    }
    .vnt-attendance-cell {
      position: relative;
      display: block;
      width: 100%;
      min-height: 22px;
      padding: 2px 3px;
      border: 1px solid transparent;
      border-radius: 4px;
      text-align: center;
      font-weight: 600;
      line-height: 16px;
    }
    .vnt-attendance-cell__badge {
      position: absolute;
      top: -7px;
      right: -5px;
      min-width: 17px;
      padding: 0 3px;
      border: 1px solid currentColor;
      border-radius: 8px;
      background: var(--card-bg);
      font-size: 8px;
      font-weight: 800;
      line-height: 13px;
      white-space: nowrap;
    }
    .vnt-attendance-cell.is-pending { border-color: #f59e0b; }
    .vnt-attendance-cell.is-pending .vnt-attendance-cell__badge { color: #b45309; }
    .vnt-attendance-cell.is-approved { border-color: #10b981; }
    .vnt-attendance-cell.is-approved .vnt-attendance-cell__badge { color: #047857; }
    .vnt-attendance-cell.is-approved_incomplete { border-color: #f97316; }
    .vnt-attendance-cell.is-approved_incomplete .vnt-attendance-cell__badge { color: #c2410c; }
    .vnt-attendance-cell.is-rejected { border-color: #ef4444; }
    .vnt-attendance-cell.is-rejected .vnt-attendance-cell__badge { color: #b91c1c; }
    @media (max-width: 1199px) {
      .vnt-attendance-legend__grid { grid-template-columns: repeat(2, minmax(240px, 1fr)); }
    }
    @media (max-width: 767px) {
      .vnt-attendance-legend__grid { grid-template-columns: 1fr; }
      .vnt-attendance-legend__group { padding: 11px; }
      .vnt-attendance-legend__item { grid-template-columns: 82px minmax(0, 1fr); }
    }
  `;
}

// Install before the first report request/render. The onload call below remains
// as an idempotent fallback when Frappe restores a cached report instance.
installAttendanceLegendStyles();

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
      "fieldname": "work_schedule_filter",
      "label": "Loại ca/kíp",
      "fieldtype": "Select",
      "options": "\nCa Hành chính\nTheo kíp\nKíp đặc biệt"
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
      "fieldname": "confirmation_status",
      "label": "Trạng thái giải trình",
      "fieldtype": "Select",
      "options": "\nCó bất thường\nChờ HR\nHR đồng ý\nHR từ chối\nĐồng ý nhưng thiếu thời gian"
    },
    {
      "fieldname": "refresh_attendance_confirmation",
      "label": "Cập nhật giải trình",
      "fieldtype": "Button",
      "btn_size": "xs",
      click: function () {
        const report = frappe.query_report;
        const vals = report.get_values() || {};
        const yesterday = frappe.datetime.add_days(frappe.datetime.get_today(), -1);
        const effective_to_date = vals.to_date && vals.to_date < yesterday
          ? vals.to_date
          : yesterday;
        frappe.call({
          method: "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm",
          args: {
            from_date: vals.from_date,
            to_date: effective_to_date,
            company: vals.company || null,
            department: vals.department || null,
            branch: vals.branch || null,
            employee: vals.employee || null,
          },
          freeze: true,
          freeze_message: __("Đang cập nhật các ngày cần HR xác nhận..."),
          callback(response) {
            const result = response.message || {};
            frappe.show_alert({
              message: __("Đã cập nhật {0} ngày bất thường, gồm {1} ngày về sớm.", [
                result["Số ngày bất thường"] || 0,
                result["Ngày làm việc về sớm"] || 0,
              ]),
              indicator: "green",
            }, 7);
            report.refresh();
          },
        });
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

    if (!isDayColumn(fieldname)) {
      return formatted;
    }

    if (isEmptyCellValue(value)) {
      return '<span style="display:block; width:100%; min-height:18px;">&nbsp;</span>';
    }

    const symbol = String(value || "");
    const palette = {
      "X": ["#e8f5e9", "#1b5e20"],
      "Đ": ["#e3f2fd", "#0d47a1"],
      "Tr": ["#fff3e0", "#e65100"],
      "Sm": ["#fff3e0", "#e65100"],
      "Tr/Sm": ["#ffe0b2", "#bf360c"],
      "KR": ["#fff8e1", "#8d6e00"],
      "KV": ["#fff8e1", "#8d6e00"],
      "V": ["#ffebee", "#b71c1c"],
      "+": ["#ede7f6", "#4527a0"],
      "+1": ["#f3e8ff", "#6b21a8"],
      "Off": ["#eceff1", "#455a64"],
      "L": ["#e0f7fa", "#006064"],
      "P": ["#f3e5f5", "#6a1b9a"],
      "H": ["#fce4ec", "#880e4f"],
      "CT": ["#e8eaf6", "#283593"],
      "Ro": ["#efebe9", "#4e342e"]
    };
    const parts = symbol.split("/");
    let colors = palette[symbol];
    if (!colors && parts.includes("V")) {
      colors = ["#ffebee", "#b71c1c"];
    }
    if (!colors && (parts.includes("KV") || parts.includes("KR"))) {
      colors = ["#fff8e1", "#8d6e00"];
    }
    if (!colors && (parts.includes("+") || parts.includes("+1"))) {
      colors = ["#ede7f6", "#4527a0"];
    }
    colors = colors || ["#f5f5f5", "#424242"];
    const review = data && data[`${fieldname}__hr_review`];
    const badgeLabels = {
      pending: "?",
      approved: "ĐY",
      approved_incomplete: "ĐY*",
      rejected: "TC"
    };
    const state = review && review.state ? review.state : "";
    const badge = state
      ? `<span class="vnt-attendance-cell__badge">${badgeLabels[state] || "?"}</span>`
      : "";
    const title = review && review.label
      ? ` title="${frappe.utils.escape_html(review.label)}"`
      : "";
    const cell = `<span class="vnt-attendance-cell${state ? ` is-${state}` : ""}"${title} style="background:${colors[0]}; color:${colors[1]};"><span>${frappe.utils.escape_html(symbol)}</span>${badge}</span>`;
    if (review && review.document_name) {
      const route = `/app/vnt-attendance-confirm/${encodeURIComponent(review.document_name)}`;
      return `<a class="vnt-attendance-cell-link" href="${route}">${cell}</a>`;
    }
    return cell;
  },

  onload: function (report) {
    installAttendanceLegendStyles();
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

(() => {
const REPORT_NAME = "BÁO CÁO TÌNH HÌNH SỬ DỤNG LAO ĐỘNG";
const EXPORT_METHOD =
  "vinatex.vnt_hr.report.báo_cáo_tình_hình_sử_dụng_lao_động.báo_cáo_tình_hình_sử_dụng_lao_động.download_excel";

const LABOR_FIELDS = [
  "begin_total",
  "begin_female",
  "increase_total",
  "increase_female",
  "decrease_total",
  "decrease_retire",
  "decrease_contract_end",
  "decrease_internal",
  "decrease_transfer",
  "end_total",
  "end_female",
  "contract_indef",
  "contract_def",
  "contract_probation",
  "contract_none",
  "contract_other",
];
const PLAN_FIELDS = ["annual_labor_plan", "plan_achievement_pct", "plan_variance"];
const VALUE_FIELDS = [...LABOR_FIELDS, ...PLAN_FIELDS];

function defaultFromDate() {
  return frappe.datetime.month_start(frappe.datetime.get_today());
}

function defaultToDate() {
  return frappe.datetime.month_end(frappe.datetime.get_today());
}

function escapeHtml(value) {
  return frappe.utils.escape_html(String(value === null || value === undefined ? "" : value));
}

function number(value) {
  return new Intl.NumberFormat("vi-VN").format(Number(value || 0));
}

function displayDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : String(value || "");
}

function totals(rows) {
  const result = LABOR_FIELDS.reduce((summary, fieldname) => {
    summary[fieldname] = (rows || []).reduce(
      (sum, row) => sum + Number(row[fieldname] || 0),
      0
    );
    return summary;
  }, {});
  const plannedRows = (rows || []).filter(
    (row) => row.annual_labor_plan !== null && row.annual_labor_plan !== undefined
  );
  if (!plannedRows.length) {
    PLAN_FIELDS.forEach((fieldname) => { result[fieldname] = null; });
    return result;
  }
  const annualPlan = plannedRows.reduce(
    (sum, row) => sum + Number(row.annual_labor_plan || 0),
    0
  );
  const plannedActual = plannedRows.reduce(
    (sum, row) => sum + Number(row.end_total || 0),
    0
  );
  result.annual_labor_plan = annualPlan;
  result.plan_achievement_pct = annualPlan ? plannedActual / annualPlan * 100 : null;
  result.plan_variance = plannedActual - annualPlan;
  return result;
}

function displayValue(fieldname, value) {
  if (PLAN_FIELDS.includes(fieldname) && (value === null || value === undefined)) return "";
  const formatted = number(value);
  return fieldname === "plan_achievement_pct" ? `${formatted}%` : formatted;
}

function dataCells(row) {
  return VALUE_FIELDS.map((fieldname) => `<td>${displayValue(fieldname, row[fieldname])}</td>`).join("");
}

function renderReport(rows, filters) {
  const summary = totals(rows);
  const body = (rows || []).map((row, index) => `
    <tr>
      <td>${index + 1}</td>
      <td class="vnt-labor-department">${escapeHtml(row.department_name || row.department)}</td>
      ${dataCells(row)}
    </tr>`).join("");

  return `
    <section class="vnt-labor-report" aria-label="Báo cáo tình hình sử dụng lao động">
      <header class="vnt-labor-letterhead">
        <div class="vnt-labor-company">${escapeHtml(filters.company).toUpperCase()}</div>
        <div class="vnt-labor-nation">
          <strong>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</strong>
          <span>Độc lập - Tự do - Hạnh phúc</span>
        </div>
        <div class="vnt-labor-report-title">
          <strong>BÁO CÁO TÌNH HÌNH SỬ DỤNG LAO ĐỘNG</strong>
          <span>Từ ngày ${displayDate(filters.from_date)} đến ngày ${displayDate(filters.to_date)}</span>
        </div>
      </header>

      <div class="vnt-labor-table-wrap">
        <table class="vnt-labor-table">
          <colgroup>
            <col class="vnt-labor-col-stt"><col class="vnt-labor-col-department">
            ${VALUE_FIELDS.map((fieldname) => `<col class="${PLAN_FIELDS.includes(fieldname) ? "vnt-labor-col-plan" : "vnt-labor-col-number"}">`).join("")}
          </colgroup>
          <thead>
            <tr>
              <th rowspan="4">STT</th>
              <th rowspan="4">Bộ phận</th>
              <th colspan="16">Tình hình sử dụng lao động</th>
              <th colspan="3" class="vnt-labor-plan-header">Kế hoạch &amp; đánh giá thực hiện</th>
            </tr>
            <tr>
              <th colspan="2">Số lao động đầu kỳ</th>
              <th colspan="2">Số lao động tăng trong kỳ</th>
              <th colspan="5">Số lao động giảm trong kỳ</th>
              <th colspan="7">Số lao động cuối kỳ</th>
              <th rowspan="3" class="vnt-labor-plan-header">LĐ kế hoạch năm</th>
              <th colspan="2" class="vnt-labor-plan-header">So sánh với kế hoạch</th>
            </tr>
            <tr>
              <th rowspan="2">Tổng số</th>
              <th rowspan="2">Trong đó nữ</th>
              <th rowspan="2">Tổng số</th>
              <th rowspan="2">Trong đó nữ</th>
              <th rowspan="2">Số lao động giảm</th>
              <th colspan="4">Trong đó</th>
              <th rowspan="2">Tổng số</th>
              <th rowspan="2">Trong đó nữ</th>
              <th colspan="5">Loại hợp đồng lao động</th>
              <th rowspan="2" class="vnt-labor-plan-header">% đạt KH</th>
              <th rowspan="2" class="vnt-labor-plan-header">Thừa (+) / Thiếu (-)</th>
            </tr>
            <tr>
              <th>Nghỉ hưu</th>
              <th>Chấm dứt HĐLĐ</th>
              <th>Điều động nội bộ</th>
              <th>Điều chuyển công tác</th>
              <th>Không xác định thời hạn</th>
              <th>Xác định thời hạn</th>
              <th>Thử việc</th>
              <th>Không giao kết HĐLĐ</th>
              <th>Khác</th>
            </tr>
          </thead>
          <tbody>
            ${body || '<tr><td colspan="21" class="vnt-labor-empty">Không có dữ liệu trong kỳ đã chọn.</td></tr>'}
          </tbody>
          <tfoot>
            <tr>
              <td></td>
              <td>TỔNG CỘNG</td>
              ${dataCells(summary)}
            </tr>
          </tfoot>
        </table>
      </div>
    </section>`;
}

function installStyles() {
  if (document.getElementById("vnt-labor-utilization-styles")) return;
  const style = document.createElement("style");
  style.id = "vnt-labor-utilization-styles";
  style.textContent = `
    .vnt-labor-report { color: #000; background: #fff; border: 1px solid var(--border-color); border-radius: 7px; overflow: hidden; font-family: "Times New Roman", Times, serif; }
    .vnt-labor-letterhead { display: flex; flex-wrap: wrap; padding: 18px 18px 14px; text-align: center; }
    .vnt-labor-company, .vnt-labor-nation { width: 50%; font-size: 14px; font-weight: 700; text-decoration: underline; text-underline-offset: 2px; }
    .vnt-labor-nation { display: flex; flex-direction: column; align-items: center; gap: 7px; }
    .vnt-labor-nation span { font-weight: 700; text-decoration: underline; text-underline-offset: 7px; }
    .vnt-labor-report-title { display: flex; flex-direction: column; gap: 4px; width: 100%; margin-top: 30px; font-size: 15px; }
    .vnt-labor-report-title strong { font-size: 16px; }
    .vnt-labor-report-title span { font-weight: 700; }
    .vnt-labor-table-wrap { max-height: calc(100vh - 280px); overflow: auto; padding: 0 16px 16px; }
    .vnt-labor-table { width: 100%; min-width: 1910px; border-collapse: separate; border-spacing: 0; table-layout: fixed; color: #000080; font-size: 12px; }
    .vnt-labor-table th, .vnt-labor-table td { height: 30px; padding: 5px 6px; text-align: center; vertical-align: middle; white-space: normal; border-right: 1px solid #8393a8; border-bottom: 1px solid #8393a8; }
    .vnt-labor-table th:first-child, .vnt-labor-table td:first-child { border-left: 1px solid #8393a8; }
    .vnt-labor-table thead { position: sticky; top: 0; z-index: 4; }
    .vnt-labor-table thead th { color: #000080; background: #c6d9f5; border-top: 1px solid #8393a8; font-weight: 700; }
    .vnt-labor-table thead th.vnt-labor-plan-header { background: #f3f7a1; }
    .vnt-labor-table tbody td { color: #111827; background: #fff; }
    .vnt-labor-table tbody tr:hover td { background: #f5f9ff; }
    .vnt-labor-table .vnt-labor-department { padding-left: 8px; text-align: left; font-weight: 600; }
    .vnt-labor-table tfoot td { color: #111827; background: #d9eaf7; font-weight: 700; }
    .vnt-labor-empty { height: 80px !important; color: #64748b !important; }
    .vnt-labor-col-stt { width: 48px; }
    .vnt-labor-col-department { width: 220px; }
    .vnt-labor-col-number { width: 92px; }
    .vnt-labor-col-plan { width: 105px; }
    @media (max-width: 768px) {
      .vnt-labor-letterhead { gap: 18px; }
      .vnt-labor-company, .vnt-labor-nation { width: 100%; }
      .vnt-labor-report-title { margin-top: 8px; }
    }
    @media print {
      .vnt-labor-report { border: 0; }
      .vnt-labor-table-wrap { max-height: none; overflow: visible; padding: 0; }
      .vnt-labor-table { min-width: 100%; font-size: 8px; }
    }
  `;
  document.head.appendChild(style);
}

frappe.query_reports[REPORT_NAME] = {
  filters: [
    {
      fieldname: "company",
      label: "Công ty",
      fieldtype: "Link",
      options: "Company",
      reqd: 1,
      default:
        frappe.defaults.get_user_default("Company") ||
        frappe.defaults.get_global_default("company"),
    },
    {
      fieldname: "from_date",
      label: "Từ ngày",
      fieldtype: "Date",
      reqd: 1,
      default: defaultFromDate(),
    },
    {
      fieldname: "to_date",
      label: "Đến ngày",
      fieldtype: "Date",
      reqd: 1,
      default: defaultToDate(),
    },
  ],

  onload(report) {
    installStyles();
    report.page.set_title("Tình hình sử dụng lao động");
    const button = report.page.add_inner_button("Tải xuống Excel", () => {
      const filters = report.get_filter_values(true);
      const query = new URLSearchParams({ filters: JSON.stringify(filters) });
      const url = frappe.urllib.get_full_url(
        `/api/method/${EXPORT_METHOD}?${query.toString()}`
      );
      window.open(url, "_blank");
    });
    button.addClass("btn-primary");
  },

  after_datatable_render() {
    const report = frappe.query_report;
    const filters = report.get_filter_values();
    const html = renderReport(report.data || [], filters || {});
    report.$report.find(".datatable").attr("aria-hidden", "true").hide();
    report.$report.find(".vnt-labor-report").remove();
    report.$report.append(html).show();
  },
};
})();

(() => {
const VNT_DETAIL_REPORT_NAME = "Chi tiết chấm công không theo ca";
const VNT_DETAIL_EXPORT_METHOD =
  "vinatex.vnt_hr.report.chi_tiết_chấm_công_không_theo_ca.chi_tiết_chấm_công_không_theo_ca.download_excel";

function vntDefaultFromDate() {
  const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
  return frappe.datetime.obj_to_str(new Date(today.getFullYear(), today.getMonth(), 1));
}

function vntEscape(value) {
  return frappe.utils.escape_html(String(value === null || value === undefined ? "" : value));
}

function vntFormatNumber(value) {
  return new Intl.NumberFormat("vi-VN", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(Number(value || 0));
}

function vntUniqueEmployeeCount(rows) {
  return new Set((rows || []).map((row) => row.employee)).size;
}

function vntGroupRows(rows) {
  const sections = [];
  const sectionMap = new Map();
  (rows || []).forEach((row) => {
    if (!sectionMap.has(row.section)) {
      const section = { name: row.section, rows: [], subgroups: [], subgroupMap: new Map() };
      sectionMap.set(row.section, section);
      sections.push(section);
    }
    const section = sectionMap.get(row.section);
    section.rows.push(row);
    const subgroupName = row.subgroup || "";
    if (!section.subgroupMap.has(subgroupName)) {
      const subgroup = { name: subgroupName, rows: [] };
      section.subgroupMap.set(subgroupName, subgroup);
      section.subgroups.push(subgroup);
    }
    section.subgroupMap.get(subgroupName).rows.push(row);
  });
  return sections;
}

function vntTimeCell(value, row, isLastPunch) {
  const extra = isLastPunch && Number(row.extra_punch_count || 0) > 0;
  const title = extra
    ? ` title="${vntEscape(`Còn ${row.extra_punch_count} lượt chấm: ${row.extra_punches || ""}`)}"`
    : "";
  const badge = extra ? `<span class="vnt-extra-punch">+${Number(row.extra_punch_count)}</span>` : "";
  return `<td${title}>${vntEscape(value)}${badge}</td>`;
}

function vntDataRow(row) {
  return `
    <tr class="vnt-detail-data-row">
      <td>${vntEscape(row.stt)}</td>
      <td>${vntEscape(row.employee_code)}</td>
      <td class="vnt-text-left">${vntEscape(row.employee_name)}</td>
      <td>${vntEscape(row.display_department)}</td>
      <td>${vntEscape(row.designation)}</td>
      <td>${vntEscape(row.work_date_display)}</td>
      <td>${vntEscape(row.weekday_label)}</td>
      ${vntTimeCell(row.in_1, row, false)}
      ${vntTimeCell(row.out_1, row, false)}
      ${vntTimeCell(row.in_2, row, false)}
      ${vntTimeCell(row.out_2, row, true)}
      <td>${vntFormatNumber(row.total_hours)}</td>
      <td>${vntFormatNumber(row.workdays)}</td>
      <td>${vntFormatNumber(row.tc1)}</td>
      <td>${vntFormatNumber(row.tc2)}</td>
      <td>${vntFormatNumber(row.tc3)}</td>
      <td>${vntFormatNumber(row.grand_total)}</td>
    </tr>`;
}

function vntGroupRow(label, className) {
  return `<tr class="${className}"><td colspan="17">${vntEscape(label)}</td></tr>`;
}

function vntRenderDetailReport(rows) {
  if (!rows || !rows.length) return "";
  const first = rows[0];
  const sections = vntGroupRows(rows);
  const employeeCount = vntUniqueEmployeeCount(rows);
  const extraPunchCount = rows.reduce(
    (total, row) => total + Number(row.extra_punch_count || 0),
    0
  );
  const duplicatePunchCount = rows.reduce(
    (total, row) => total + Number(row.duplicate_punch_count || 0),
    0
  );
  const body = [];
  body.push(vntGroupRow(`${first.company_name} (${employeeCount})`, "vnt-company-row"));
  sections.forEach((section) => {
    body.push(
      vntGroupRow(
        `${section.name} (${vntUniqueEmployeeCount(section.rows)})`,
        "vnt-section-row"
      )
    );
    section.subgroups.forEach((subgroup) => {
      if (subgroup.name) {
        body.push(
          vntGroupRow(
            `${subgroup.name} (${vntUniqueEmployeeCount(subgroup.rows)})`,
            "vnt-subgroup-row"
          )
        );
      }
      subgroup.rows.forEach((row) => body.push(vntDataRow(row)));
    });
  });

  const warning = extraPunchCount
    ? `<div class="vnt-detail-note vnt-detail-warning">Có ${extraPunchCount} lượt chấm vượt quá 4 lần/ngày. Di chuột vào cột Ra 2 để xem chi tiết; tệp Excel có ghi chú tương ứng.</div>`
    : "";
  const duplicateNote = duplicatePunchCount
    ? `<div class="vnt-detail-note">Hệ thống đã loại ${duplicatePunchCount} lượt quẹt trùng cùng trạng thái xếp ca trong vòng 5 phút trước khi ghép cặp Vào/Ra.</div>`
    : "";

  return `
    <div class="vnt-detail-attendance">
      <div class="vnt-detail-heading">
        <div class="vnt-detail-title">CHI TIẾT CHẤM CÔNG KHÔNG THEO CA</div>
        <div class="vnt-detail-subtitle">Từ ngày ${vntEscape(
          frappe.datetime.str_to_user(first.from_date)
        )} đến ngày ${vntEscape(frappe.datetime.str_to_user(first.to_date))}</div>
      </div>
      ${warning}
      ${duplicateNote}
      <div class="vnt-detail-table-wrap">
        <table class="vnt-detail-table">
          <colgroup>
            <col class="vnt-col-stt"><col class="vnt-col-code"><col class="vnt-col-name">
            <col class="vnt-col-department"><col class="vnt-col-designation"><col class="vnt-col-date">
            <col class="vnt-col-weekday"><col class="vnt-col-time"><col class="vnt-col-time">
            <col class="vnt-col-time"><col class="vnt-col-time"><col class="vnt-col-number">
            <col class="vnt-col-number"><col class="vnt-col-small"><col class="vnt-col-small">
            <col class="vnt-col-small"><col class="vnt-col-number">
          </colgroup>
          <thead>
            <tr>
              <th>STT</th><th>Mã N.Viên</th><th>Tên N.Viên</th><th>Phòng ban</th>
              <th>Chức vụ</th><th>Ngày</th><th>Thứ</th><th>Vào 1</th><th>Ra 1</th>
              <th>Vào 2</th><th>Ra 2</th><th>Tổng giờ</th><th>Ngày Công</th>
              <th>TC1</th><th>TC2</th><th>TC3</th><th>Tổng cộng</th>
            </tr>
          </thead>
          <tbody>${body.join("")}</tbody>
        </table>
      </div>
      <div class="vnt-detail-note">Nguồn giờ: Employee Checkin. Ca kế hoạch chỉ dùng để xếp lượt chấm qua đêm vào đúng ngày công. Báo cáo tính đến phút đúng như giờ HH:mm đang hiển thị: Tổng giờ = tổng thời gian của các cặp Vào/Ra đầy đủ, làm tròn 3 số; Ngày Công = Tổng giờ / 8, làm tròn 3 số. TC1–TC3 giữ bằng 0 theo file mẫu.</div>
    </div>`;
}

function vntInstallDetailStyles() {
  if (document.getElementById("vnt-detail-attendance-styles")) return;
  const style = document.createElement("style");
  style.id = "vnt-detail-attendance-styles";
  style.textContent = `
    .vnt-detail-attendance { color: var(--text-color); background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; }
    .vnt-detail-heading { padding: 16px 20px 12px; text-align: center; background: var(--card-bg); }
    .vnt-detail-title { font-size: 16px; font-weight: 700; color: var(--heading-color); }
    .vnt-detail-subtitle { margin-top: 4px; font-size: 13px; font-weight: 600; }
    .vnt-detail-table-wrap { overflow: auto; max-height: calc(100vh - 290px); border-top: 1px solid var(--border-color); }
    .vnt-detail-table { width: 100%; min-width: 1420px; table-layout: fixed; border-collapse: separate; border-spacing: 0; font-family: Arial, sans-serif; font-size: 12px; }
    .vnt-detail-table th, .vnt-detail-table td { height: 30px; padding: 5px 7px; text-align: center; vertical-align: middle; white-space: nowrap; border-right: 1px solid #9ca3af; border-bottom: 1px solid #9ca3af; }
    .vnt-detail-table th:first-child, .vnt-detail-table td:first-child { border-left: 1px solid #9ca3af; }
    .vnt-detail-table thead th { position: sticky; top: 0; z-index: 4; color: #111827; background: #f3f4f6; font-weight: 700; border-top: 1px solid #9ca3af; }
    .vnt-detail-table .vnt-company-row td, .vnt-detail-table .vnt-section-row td, .vnt-detail-table .vnt-subgroup-row td { height: 28px; text-align: left; color: #111827; background: #d1d5db; font-weight: 700; }
    .vnt-detail-table .vnt-subgroup-row td { padding-left: 20px; background: #e5e7eb; }
    .vnt-detail-data-row:hover td { background: var(--bg-light-gray); }
    .vnt-text-left { text-align: left !important; overflow: hidden; text-overflow: ellipsis; }
    .vnt-extra-punch { display: inline-flex; margin-left: 4px; padding: 0 4px; border-radius: 8px; color: #9f1239; background: #ffe4e6; font-size: 10px; font-weight: 700; }
    .vnt-detail-note { padding: 9px 14px; color: var(--text-muted); background: var(--subtle-fg); font-size: 11px; line-height: 1.45; }
    .vnt-detail-warning { color: #92400e; background: #fffbeb; border-top: 1px solid #fde68a; }
    .vnt-col-stt { width: 52px; } .vnt-col-code { width: 108px; } .vnt-col-name { width: 180px; }
    .vnt-col-department { width: 120px; } .vnt-col-designation { width: 130px; } .vnt-col-date { width: 102px; }
    .vnt-col-weekday { width: 58px; } .vnt-col-time { width: 66px; } .vnt-col-number { width: 92px; } .vnt-col-small { width: 58px; }
    @media print { .vnt-detail-table-wrap { max-height: none; overflow: visible; } .vnt-detail-attendance { border: 0; } }
  `;
  document.head.appendChild(style);
}

frappe.query_reports[VNT_DETAIL_REPORT_NAME] = {
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
      default: vntDefaultFromDate(),
    },
    {
      fieldname: "to_date",
      label: "Đến ngày",
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.get_today(),
    },
    {
      fieldname: "area",
      label: "Khối",
      fieldtype: "Select",
      options: "\nHC\nVăn phòng\nXưởng",
    },
    {
      fieldname: "shift_group",
      label: "Kíp",
      fieldtype: "Link",
      options: "VNT Shift Group",
    },
    {
      fieldname: "department",
      label: "Phòng ban",
      fieldtype: "Link",
      options: "Department",
    },
    {
      fieldname: "branch",
      label: "Chi nhánh",
      fieldtype: "Link",
      options: "Branch",
    },
    {
      fieldname: "employee",
      label: "Nhân viên",
      fieldtype: "Link",
      options: "Employee",
      get_query: () => {
        const company = frappe.query_report.get_filter_value("company");
        return { filters: company ? { company } : {} };
      },
    },
  ],

  onload(report) {
    vntInstallDetailStyles();
    const button = report.page.add_inner_button("Xuất Excel", () => {
      const filters = report.get_filter_values(true);
      const query = new URLSearchParams({ filters: JSON.stringify(filters) });
      const url = frappe.urllib.get_full_url(
        `/api/method/${VNT_DETAIL_EXPORT_METHOD}?${query.toString()}`
      );
      window.open(url, "_blank");
    });
    button.addClass("btn-primary");
  },

  after_datatable_render() {
    const report = frappe.query_report;
    const html = vntRenderDetailReport(report.data || []);
    if (!html) return;
    // Giữ DataTable ở trạng thái ẩn để các chức năng chuẩn của
    // Query Report vẫn hoạt động; bảng HTML bên dưới là giao diện chính.
    report.$report.find(".datatable").attr("aria-hidden", "true").hide();
    report.$report.find(".vnt-detail-attendance").remove();
    report.$report.append(html).show();
  },
};
})();

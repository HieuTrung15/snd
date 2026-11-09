(() => {
  const REPORT_NAME = "Báo cáo công hàng tháng";
  const EXPORT_METHOD =
    "vinatex.vnt_hr.report.báo_cáo_công_hàng_tháng.báo_cáo_công_hàng_tháng.download_excel";
  const CONFIRM_METHOD =
    "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm";
  const SUMMARY_COLUMNS = [
    ["tot_work_days", "X (S,C) + CT"], ["tot_work_hours", "h làm việc"],
    ["tot_sick", "Ô"], ["tot_night", "Đ"], ["tot_sunday", "CN"],
    ["tot_holiday", "L"], ["tot_special_group", "NL, NM, CTDH"],
    ["tot_paid_group", "P, ND, CL"], ["tot_family_leave", "CH, TL"], ["tot_comp_leave", "NB"],
    ["tot_unpaid_reason", "R0"], ["tot_unpaid_no_reason", "L0"],
    ["rating", "Xếp loại"], ["score", "Điểm"],
  ];

  function escapeHtml(value) {
    return frappe.utils.escape_html(String(value === null || value === undefined ? "" : value));
  }

  function dayFields(row) {
    return Object.keys(row || {}).filter((key) => /^d\d{2}$/.test(key)).sort();
  }

  function formatNumber(value, decimals = 2) {
    if (value === "" || value === null || value === undefined) return "";
    const number = Number(value || 0);
    return new Intl.NumberFormat("vi-VN", {
      minimumFractionDigits: Number.isInteger(number) ? 0 : decimals,
      maximumFractionDigits: decimals,
    }).format(number);
  }

  function fittedWidth(values, minimum, maximum, characterWidth = 7) {
    const longest = Math.max(0, ...values.map((value) => String(value || "").length));
    return Math.min(maximum, Math.max(minimum, longest * characterWidth + 20));
  }

  function groupRows(rows) {
    const result = [];
    const sectionMap = new Map();
    (rows || []).forEach((row) => {
      if (!sectionMap.has(row.section)) {
        const section = { name: row.section, subgroups: [], subgroupMap: new Map() };
        sectionMap.set(row.section, section);
        result.push(section);
      }
      const section = sectionMap.get(row.section);
      const subgroupName = row.subgroup || "";
      if (!section.subgroupMap.has(subgroupName)) {
        const subgroup = { name: subgroupName, rows: [] };
        section.subgroupMap.set(subgroupName, subgroup);
        section.subgroups.push(subgroup);
      }
      section.subgroupMap.get(subgroupName).rows.push(row);
    });
    return result;
  }

  function dayCell(row, fieldname) {
    const value = row[fieldname] || "";
    const state = row[`${fieldname}__state`] || "";
    const reviewState = row[`${fieldname}__review_state`] || "";
    const labels = [row[`${fieldname}__label`], row[`${fieldname}__review_label`]].filter(Boolean);
    const badge = reviewState
      ? `<span class="vnt-monthly-review is-${escapeHtml(reviewState)}">${{
          pending: "?", approved: "ĐY", approved_incomplete: "ĐY*", rejected: "TC",
        }[reviewState] || "?"}</span>`
      : "";
    const content = `<span class="vnt-monthly-day ${state ? `is-${state}` : ""}" title="${escapeHtml(labels.join(" — "))}">${escapeHtml(value)}${badge}</span>`;
    return `<td class="vnt-monthly-day-cell">${content}</td>`;
  }

  // Bấm tên nhân viên mở phiếu giải trình của cả kỳ; chưa có phiếu (hoặc có
  // nhiều phiếu) thì mở danh sách đã lọc sẵn theo nhân viên và tháng.
  function nameCell(row) {
    const name = escapeHtml(row.employee_name);
    if (!row.can_open_confirmation || !row.employee) {
      return `<td class="vnt-monthly-name">${name}</td>`;
    }
    const confirmDoc = row.confirm_document ? String(row.confirm_document) : "";
    const href = confirmDoc
      ? `/app/vnt-attendance-confirm/${encodeURIComponent(confirmDoc)}`
      : "/app/vnt-attendance-confirm";
    const hint = confirmDoc
      ? `Mở phiếu giải trình ${confirmDoc}`
      : "Mở danh sách giải trình đã lọc theo nhân viên và tháng";
    return `<td class="vnt-monthly-name"><a class="vnt-monthly-name-link" href="${href}" title="${escapeHtml(hint)}" data-employee="${escapeHtml(row.employee)}" data-confirm="${escapeHtml(confirmDoc)}"><span class="vnt-monthly-name-link__text">${name}</span><span class="vnt-monthly-name-link__icon">→</span></a></td>`;
  }

  function renderReport(rows, filters) {
    const first = (rows || [])[0] || {};
    const days = dayFields(first);
    const totalColumns = 5 + days.length + SUMMARY_COLUMNS.length;
    const body = [];
    const year = Number(filters.year || new Date().getFullYear());
    const month = Number(filters.month || new Date().getMonth() + 1);
    const widths = {
      name: fittedWidth(["Tên nhân viên", ...rows.map((row) => row.employee_name)], 150, 260),
      code: fittedWidth(["Mã nhân viên", ...rows.map((row) => row.employee_code)], 100, 145),
      department: fittedWidth(["Vị trí/ Bộ phận", ...rows.map((row) => row.department_code)], 95, 180),
      shift: fittedWidth(["Kíp", ...rows.map((row) => row.shift_label)], 90, 320),
    };
    const colgroup = `<colgroup>
      <col style="width:45px"><col style="width:${widths.code}px"><col style="width:${widths.name}px">
      <col style="width:${widths.department}px"><col style="width:${widths.shift}px">
      ${days.map(() => '<col style="width:42px">').join("")}
      ${SUMMARY_COLUMNS.map(([, label]) => `<col style="width:${fittedWidth([label], 54, 120)}px">`).join("")}
    </colgroup>`;
    let sequence = 0;
    groupRows(rows).forEach((section) => {
      body.push(`<tr class="vnt-monthly-group"><td colspan="${totalColumns}">${escapeHtml(section.name)}</td></tr>`);
      section.subgroups.forEach((subgroup) => {
        if (subgroup.name) {
          body.push(`<tr class="vnt-monthly-subgroup"><td colspan="${totalColumns}">${escapeHtml(subgroup.name)}</td></tr>`);
        }
        subgroup.rows.forEach((row) => {
          sequence += 1;
          body.push(`<tr>
            <td>${sequence}</td><td class="vnt-monthly-code">${escapeHtml(row.employee_code)}</td>
            ${nameCell(row)}
            <td class="vnt-monthly-department">${escapeHtml(row.department_code)}</td><td class="vnt-monthly-shift">${escapeHtml(row.shift_label)}</td>
            ${days.map((fieldname) => dayCell(row, fieldname)).join("")}
            ${SUMMARY_COLUMNS.map(([fieldname]) => `<td>${["rating", "score"].includes(fieldname) ? escapeHtml(row[fieldname]) : formatNumber(row[fieldname])}</td>`).join("")}
          </tr>`);
        });
      });
    });

    const totals = SUMMARY_COLUMNS.map(([fieldname]) => {
      if (["rating", "score"].includes(fieldname)) return "";
      return formatNumber((rows || []).reduce((sum, row) => sum + Number(row[fieldname] || 0), 0));
    });
    return `
      <section class="vnt-monthly-report" data-vnt-report-ui aria-label="Báo cáo công hàng tháng" style="--vnt-index-width:45px;--vnt-code-width:${widths.code}px">
        <div class="vnt-monthly-legend">
          <div><b>R0</b><span>Nghỉ không hưởng lương (có lý do)</span></div><div><b>1-7</b><span>Thời gian làm việc không đủ công</span></div><div><b>C</b><span>Ca chiều (14h - 22h)</span></div>
          <div><b>L0</b><span>Nghỉ không lý do</span></div><div><b>CN</b><span>Chủ nhật</span></div><div><b>Đ</b><span>Ca đêm (22h - 6h)</span></div>
          <div><b>X</b><span>Ca hành chính</span></div><div><b>S</b><span>Ca sáng (6h - 14h)</span></div><div><b>NB</b><span>Nghỉ bù</span></div>
          <div><b>Ô</b><span>Nghỉ ốm</span></div><div><b>L / NL</b><span>Lễ / Nghỉ lễ</span></div><div><b>NM</b><span>Nghỉ mát</span></div>
          <div><b>CH / TL</b><span>Cưới hỏi / Tang lễ</span></div><div><b>P</b><span>Nghỉ phép</span></div>
        </div>
        <div class="vnt-monthly-table-wrap"><table class="vnt-monthly-table">${colgroup}
          <thead><tr>
            <th rowspan="2">STT</th><th rowspan="2">Mã nhân viên</th><th rowspan="2">Tên nhân viên</th>
            <th rowspan="2">Vị trí/ Bộ phận công tác</th><th rowspan="2">Kíp</th>
            <th colspan="${days.length}">T ${month}/${year}</th>
            ${SUMMARY_COLUMNS.map(([, label]) => `<th rowspan="2">${escapeHtml(label)}</th>`).join("")}
          </tr><tr>${days.map((fieldname) => {
            const day = Number(fieldname.slice(1));
            const isSunday = new Date(year, month - 1, day).getDay() === 0;
            return `<th class="${isSunday ? "is-sunday" : ""}">${day}</th>`;
          }).join("")}</tr></thead>
          <tbody>${body.join("") || `<tr><td colspan="${totalColumns}" class="vnt-monthly-empty">Không có dữ liệu phù hợp bộ lọc.</td></tr>`}</tbody>
          <tfoot><tr><td colspan="5">TỔNG CỘNG</td>${days.map(() => "<td></td>").join("")}${totals.map((value) => `<td>${value}</td>`).join("")}</tr></tfoot>
        </table></div>
      </section>`;
  }

  function installStyles() {
    if (document.getElementById("vnt-monthly-attendance-styles")) return;
    const style = document.createElement("style");
    style.id = "vnt-monthly-attendance-styles";
    style.textContent = `
      .vnt-monthly-report{--vnt-grid-color:var(--gray-400,#c7c7c7);color:var(--text-color);background:var(--card-bg);border:1px solid var(--vnt-grid-color);border-radius:10px;overflow:hidden;font-family:Arial,sans-serif}
      .vnt-monthly-table-wrap{max-height:calc(100vh - 375px);overflow:auto}.vnt-monthly-table{min-width:100%;width:max-content;border-collapse:separate;border-spacing:0;table-layout:fixed;font-size:11px}
      .vnt-monthly-table th,.vnt-monthly-table td{box-sizing:border-box;height:28px;padding:3px 5px;text-align:center;vertical-align:middle;border-right:1px solid var(--vnt-grid-color);border-bottom:1px solid var(--vnt-grid-color);background-color:var(--card-bg,#fff);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .vnt-monthly-table th:first-child,.vnt-monthly-table td:first-child{border-left:1px solid var(--vnt-grid-color)}.vnt-monthly-table thead{position:sticky;top:0;z-index:5}.vnt-monthly-table thead th{background-color:var(--control-bg,#f4f5f6);color:var(--heading-color);border-top:1px solid var(--vnt-grid-color);font-weight:700;white-space:normal}.vnt-monthly-table thead .is-sunday{color:#fff;background-color:#ef4444}
      .vnt-monthly-table thead tr:first-child>th:nth-child(1){position:sticky;left:0;z-index:9}.vnt-monthly-table thead tr:first-child>th:nth-child(2){position:sticky;left:var(--vnt-index-width);z-index:9}.vnt-monthly-table thead tr:first-child>th:nth-child(3){position:sticky;left:calc(var(--vnt-index-width) + var(--vnt-code-width));z-index:9}
      .vnt-monthly-table tbody tr:not(.vnt-monthly-group):not(.vnt-monthly-subgroup)>td:nth-child(1){position:sticky;left:0;z-index:3;background-color:var(--card-bg,#fff)}.vnt-monthly-table tbody tr:not(.vnt-monthly-group):not(.vnt-monthly-subgroup)>td:nth-child(2){position:sticky;left:var(--vnt-index-width);z-index:3;background-color:var(--card-bg,#fff)}.vnt-monthly-table tbody tr:not(.vnt-monthly-group):not(.vnt-monthly-subgroup)>td:nth-child(3){position:sticky;left:calc(var(--vnt-index-width) + var(--vnt-code-width));z-index:3;background-color:var(--card-bg,#fff)}
      .vnt-monthly-name,.vnt-monthly-shift{text-align:left!important}.vnt-monthly-shift{font-weight:600}.vnt-monthly-day-cell{padding:3px!important}.vnt-monthly-group td,.vnt-monthly-subgroup td{text-align:left!important;background-color:var(--control-bg-on-gray,#e2e4e7)!important;color:var(--heading-color);font-weight:700}.vnt-monthly-subgroup td{padding-left:20px;background-color:var(--subtle-accent,#f8f8f8)!important}
      .vnt-monthly-day{position:relative;display:flex;min-height:22px;align-items:center;justify-content:center;font-weight:600}.vnt-monthly-day.is-missing_in{background:#f59e0b}.vnt-monthly-day.is-missing_out{background:#fde047}.vnt-monthly-day.is-absent{color:#fff;background:#ef4444}.vnt-monthly-name-link{display:inline-flex;align-items:center;gap:4px;max-width:100%;color:inherit!important;font-weight:600;text-decoration:none!important}.vnt-monthly-name-link__text{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.vnt-monthly-name-link__icon{flex:0 0 auto;font-size:11px;opacity:0;transition:opacity .15s ease}.vnt-monthly-name-link:hover{color:var(--blue-500,#0289f7)!important;text-decoration:underline!important}.vnt-monthly-name-link:hover .vnt-monthly-name-link__icon{opacity:.85}.vnt-monthly-review{position:absolute;top:-7px;right:-6px;padding:0 3px;border-radius:7px;background:var(--card-bg,#fff);border:1px solid currentColor;font-size:8px;line-height:12px}.vnt-monthly-review.is-approved{color:#047857}.vnt-monthly-review.is-approved_incomplete{color:#c2410c}.vnt-monthly-review.is-rejected{color:#b91c1c}.vnt-monthly-review.is-pending{color:#b45309}
      .vnt-monthly-table tfoot td{background-color:var(--control-bg,#f4f5f6);color:var(--heading-color);font-weight:700}.vnt-monthly-empty{height:80px!important;color:var(--text-muted)}.vnt-monthly-legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:4px 18px;padding:10px 16px;border-bottom:1px solid var(--vnt-grid-color);background:var(--card-bg);font-family:"Times New Roman",serif;font-style:italic}.vnt-monthly-legend div{display:grid;grid-template-columns:52px 1fr;gap:8px}.vnt-monthly-legend b{text-align:center}
      @media(max-width:768px){.vnt-monthly-legend{grid-template-columns:1fr}}@media print{.vnt-monthly-table-wrap{max-height:none;overflow:visible}.vnt-monthly-report{border:0}}
    `;
    document.head.appendChild(style);
  }

  function updateDateFilters(report) {
    const values = report.get_values() || {};
    const year = Number(values.year);
    const month = Number(values.month);
    if (!year || !month) return;
    report.set_filter_value("from_date", frappe.datetime.obj_to_str(new Date(year, month - 1, 1)));
    report.set_filter_value("to_date", frappe.datetime.obj_to_str(new Date(year, month, 0)));
  }

  const now = new Date();
  frappe.query_reports[REPORT_NAME] = {
    filters: [
      { fieldname:"company",label:"Công ty",fieldtype:"Link",options:"Company",reqd:1,default:frappe.defaults.get_user_default("Company")||frappe.defaults.get_global_default("company") },
      { fieldname:"month",label:"Tháng",fieldtype:"Select",options:"01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",reqd:1,default:String(now.getMonth()+1).padStart(2,"0"),on_change(){updateDateFilters(frappe.query_report);frappe.query_report.refresh();} },
      { fieldname:"year",label:"Năm",fieldtype:"Int",reqd:1,default:now.getFullYear(),on_change(){updateDateFilters(frappe.query_report);frappe.query_report.refresh();} },
      { fieldname:"department",label:"Phòng ban",fieldtype:"Link",options:"Department" },
      { fieldname:"branch",label:"Chi nhánh",fieldtype:"Link",options:"Branch" },
      { fieldname:"employee",label:"Nhân viên",fieldtype:"Link",options:"Employee" },
      { fieldname:"work_schedule_filter",label:"Loại ca/kíp",fieldtype:"Select",options:"\nCa Hành chính\nTheo kíp\nKíp đặc biệt" },
      { fieldname:"from_date",label:"Từ ngày",fieldtype:"Date",hidden:1 },
      { fieldname:"to_date",label:"Đến ngày",fieldtype:"Date",hidden:1 },
    ],
    onload(report) {
      installStyles();
      updateDateFilters(report);
      const exportButton = report.page.add_inner_button("Tải xuống Excel", () => {
        const query = new URLSearchParams({ filters: JSON.stringify(report.get_filter_values(true)) });
        window.open(frappe.urllib.get_full_url(`/api/method/${EXPORT_METHOD}?${query.toString()}`), "_blank");
      });
      exportButton.addClass("btn-primary");
      report.page.add_inner_button("Cập nhật giải trình", () => {
        const values = report.get_filter_values(true);
        const yesterday = frappe.datetime.add_days(frappe.datetime.get_today(), -1);
        frappe.call({ method:CONFIRM_METHOD,args:{ from_date:values.from_date,to_date:values.to_date<yesterday?values.to_date:yesterday,company:values.company||null,department:values.department||null,branch:values.branch||null,employee:values.employee||null },freeze:true,freeze_message:__("Đang cập nhật các ô cần giải trình..."),callback(){report.refresh();} });
      });
    },
    after_datatable_render() {
      const report = frappe.query_report;
      report.$report.find(".datatable").attr("aria-hidden", "true").hide();
      report.$report.find(".vnt-monthly-report").remove();
      report.$report.append(renderReport(report.data || [], report.get_filter_values() || {})).show();
      report.$report.off("click.vntMonthlyName").on("click.vntMonthlyName", ".vnt-monthly-name-link", function (event) {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.which === 2) {
          return; // Để trình duyệt tự mở tab mới theo href.
        }
        event.preventDefault();
        const confirmDoc = this.getAttribute("data-confirm");
        if (confirmDoc) {
          frappe.set_route("Form", "VNT Attendance Confirm", confirmDoc);
          return;
        }
        const values = report.get_filter_values() || {};
        frappe.route_options = { employee: this.getAttribute("data-employee") };
        if (values.month) frappe.route_options.month = values.month;
        if (values.year) frappe.route_options.year = values.year;
        frappe.set_route("List", "VNT Attendance Confirm");
      });
    },
  };
})();

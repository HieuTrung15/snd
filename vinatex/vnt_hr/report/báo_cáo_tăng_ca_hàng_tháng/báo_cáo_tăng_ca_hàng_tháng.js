(() => {
  const REPORT_NAME = "Báo cáo tăng ca hàng tháng";
  const EXPORT_METHOD =
    "vinatex.vnt_hr.report.báo_cáo_tăng_ca_hàng_tháng.báo_cáo_tăng_ca_hàng_tháng.download_excel";
  const CONFIRM_METHOD =
    "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm";
  const TOTAL_COLUMNS = [
    ["tot_overtime_normal", "Ngày thường"],
    ["tot_overtime_off", "Ngày nghỉ"],
    ["tot_overtime_holiday", "Ngày lễ"],
  ];

  function escapeHtml(value) {
    return frappe.utils.escape_html(String(value === null || value === undefined ? "" : value));
  }

  function formatNumber(value) {
    if (value === "" || value === null || value === undefined) return "";
    const number = Number(value || 0);
    return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(number);
  }

  function fittedWidth(values, minimum, maximum, characterWidth = 7) {
    const longest = Math.max(0, ...values.map((value) => String(value || "").length));
    return Math.min(maximum, Math.max(minimum, longest * characterWidth + 20));
  }

  function dayFields(row) {
    return Object.keys(row || {}).filter((key) => /^d\d{2}$/.test(key)).sort();
  }

  function groupRows(rows) {
    const sections = [];
    const map = new Map();
    (rows || []).forEach((row) => {
      if (!map.has(row.section)) {
        const section = { name: row.section, subgroups: [], map: new Map() };
        map.set(row.section, section);
        sections.push(section);
      }
      const section = map.get(row.section);
      const subgroupName = row.subgroup || "";
      if (!section.map.has(subgroupName)) {
        const subgroup = { name: subgroupName, rows: [] };
        section.map.set(subgroupName, subgroup);
        section.subgroups.push(subgroup);
      }
      section.map.get(subgroupName).rows.push(row);
    });
    return sections;
  }

  function dayCell(row, fieldname) {
    const value = row[fieldname];
    const state = row[`${fieldname}__state`] || "";
    const title = [row[`${fieldname}__label`], row[`${fieldname}__review_label`]].filter(Boolean).join(" — ");
    const badge = value && state
      ? `<span class="vnt-overtime-badge">${{
          unreviewed: "!", pending: "?", approved: "ĐY", approved_incomplete: "ĐY*", rejected: "TC",
        }[state] || "!"}</span>`
      : "";
    const content = `<span class="vnt-overtime-day ${state ? `is-${state}` : ""}" title="${escapeHtml(title)}">${formatNumber(value)}${badge}</span>`;
    return `<td class="vnt-overtime-day-cell">${content}</td>`;
  }

  // Bấm tên nhân viên mở phiếu giải trình của cả kỳ; chưa có phiếu (hoặc có
  // nhiều phiếu) thì mở danh sách đã lọc sẵn theo nhân viên và tháng.
  function nameCell(row) {
    const name = escapeHtml(row.employee_name);
    if (!row.can_open_confirmation || !row.employee) {
      return `<td class="vnt-overtime-name">${name}</td>`;
    }
    const confirmDoc = row.confirm_document ? String(row.confirm_document) : "";
    const href = confirmDoc
      ? `/app/vnt-attendance-confirm/${encodeURIComponent(confirmDoc)}`
      : "/app/vnt-attendance-confirm";
    const hint = confirmDoc
      ? `Mở phiếu giải trình ${confirmDoc}`
      : "Mở danh sách giải trình đã lọc theo nhân viên và tháng";
    return `<td class="vnt-overtime-name"><a class="vnt-overtime-name-link" href="${href}" title="${escapeHtml(hint)}" data-employee="${escapeHtml(row.employee)}" data-confirm="${escapeHtml(confirmDoc)}"><span class="vnt-overtime-name-link__text">${name}</span><span class="vnt-overtime-name-link__icon">→</span></a></td>`;
  }

  function renderReport(rows, filters) {
    const first = (rows || [])[0] || {};
    const days = dayFields(first);
    const totalColumns = 5 + days.length + TOTAL_COLUMNS.length;
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
      ${TOTAL_COLUMNS.map(([, label]) => `<col style="width:${fittedWidth([label], 70, 115)}px">`).join("")}
    </colgroup>`;
    let sequence = 0;
    groupRows(rows).forEach((section) => {
      body.push(`<tr class="vnt-overtime-group"><td colspan="${totalColumns}">${escapeHtml(section.name)}</td></tr>`);
      section.subgroups.forEach((subgroup) => {
        if (subgroup.name) body.push(`<tr class="vnt-overtime-subgroup"><td colspan="${totalColumns}">${escapeHtml(subgroup.name)}</td></tr>`);
        subgroup.rows.forEach((row) => {
          sequence += 1;
          body.push(`<tr><td>${sequence}</td><td class="vnt-overtime-code">${escapeHtml(row.employee_code)}</td>${nameCell(row)}<td class="vnt-overtime-department">${escapeHtml(row.department_code)}</td><td class="vnt-overtime-shift">${escapeHtml(row.shift_label)}</td>${days.map((fieldname) => dayCell(row, fieldname)).join("")}${TOTAL_COLUMNS.map(([fieldname]) => `<td>${formatNumber(row[fieldname])}</td>`).join("")}</tr>`);
        });
      });
    });
    const totals = TOTAL_COLUMNS.map(([fieldname]) => formatNumber((rows || []).reduce((sum, row) => sum + Number(row[fieldname] || 0), 0)));
    return `<section class="vnt-overtime-report" data-vnt-report-ui aria-label="Báo cáo tăng ca hàng tháng" style="--vnt-index-width:45px;--vnt-code-width:${widths.code}px">
      <div class="vnt-overtime-table-wrap"><table class="vnt-overtime-table">${colgroup}<thead><tr>
        <th rowspan="2">STT</th><th rowspan="2">Mã nhân viên</th><th rowspan="2">Tên nhân viên</th><th rowspan="2">Vị trí/ Bộ phận công tác</th><th rowspan="2">Kíp</th>
        <th colspan="${days.length}">T ${month}/${year}</th>${TOTAL_COLUMNS.map(([, label]) => `<th rowspan="2">${escapeHtml(label)}</th>`).join("")}
      </tr><tr>${days.map((fieldname) => { const day=Number(fieldname.slice(1)); const sunday=new Date(year,month-1,day).getDay()===0; return `<th class="${sunday?"is-sunday":""}">${day}</th>`; }).join("")}</tr></thead>
      <tbody>${body.join("") || `<tr><td colspan="${totalColumns}" class="vnt-overtime-empty">Không có dữ liệu phù hợp bộ lọc.</td></tr>`}</tbody>
      <tfoot><tr><td colspan="5">TỔNG</td>${days.map(() => "<td></td>").join("")}${totals.map((value) => `<td>${value}</td>`).join("")}</tr></tfoot></table></div>
      <div class="vnt-overtime-legend"><span class="is-unreviewed">Chưa có phiếu giải trình</span><span class="is-pending">Chờ HR</span><span class="is-approved">HR đồng ý</span><span class="is-rejected">HR từ chối</span><small>Giờ tăng ca được làm tròn theo vân tay và ca kế hoạch.</small></div>
    </section>`;
  }

  function installStyles() {
    if (document.getElementById("vnt-overtime-report-styles")) return;
    const style = document.createElement("style");
    style.id = "vnt-overtime-report-styles";
    style.textContent = `
      .vnt-overtime-report{--vnt-grid-color:var(--gray-400,#c7c7c7);color:var(--text-color);background:var(--card-bg);border:1px solid var(--vnt-grid-color);border-radius:10px;overflow:hidden;font-family:Arial,sans-serif}.vnt-overtime-table-wrap{max-height:calc(100vh - 285px);overflow:auto}.vnt-overtime-table{min-width:100%;width:max-content;border-collapse:separate;border-spacing:0;table-layout:fixed;font-size:11px}
      .vnt-overtime-table th,.vnt-overtime-table td{box-sizing:border-box;height:28px;padding:3px 5px;text-align:center;vertical-align:middle;border-right:1px solid var(--vnt-grid-color);border-bottom:1px solid var(--vnt-grid-color);background-color:var(--card-bg,#fff);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.vnt-overtime-table th:first-child,.vnt-overtime-table td:first-child{border-left:1px solid var(--vnt-grid-color)}.vnt-overtime-table thead{position:sticky;top:0;z-index:5}.vnt-overtime-table thead th{background-color:var(--control-bg,#f4f5f6);color:var(--heading-color);border-top:1px solid var(--vnt-grid-color);font-weight:700;white-space:normal}.vnt-overtime-table thead .is-sunday{color:#fff;background-color:#ef4444}
      .vnt-overtime-table thead tr:first-child>th:nth-child(1){position:sticky;left:0;z-index:9}.vnt-overtime-table thead tr:first-child>th:nth-child(2){position:sticky;left:var(--vnt-index-width);z-index:9}.vnt-overtime-table thead tr:first-child>th:nth-child(3){position:sticky;left:calc(var(--vnt-index-width) + var(--vnt-code-width));z-index:9}
      .vnt-overtime-table tbody tr:not(.vnt-overtime-group):not(.vnt-overtime-subgroup)>td:nth-child(1){position:sticky;left:0;z-index:3;background-color:var(--card-bg,#fff)}.vnt-overtime-table tbody tr:not(.vnt-overtime-group):not(.vnt-overtime-subgroup)>td:nth-child(2){position:sticky;left:var(--vnt-index-width);z-index:3;background-color:var(--card-bg,#fff)}.vnt-overtime-table tbody tr:not(.vnt-overtime-group):not(.vnt-overtime-subgroup)>td:nth-child(3){position:sticky;left:calc(var(--vnt-index-width) + var(--vnt-code-width));z-index:3;background-color:var(--card-bg,#fff)}
      .vnt-overtime-name,.vnt-overtime-shift{text-align:left!important}.vnt-overtime-shift{font-weight:600}.vnt-overtime-day-cell{padding:3px!important}.vnt-overtime-group td,.vnt-overtime-subgroup td{text-align:left!important;background-color:var(--control-bg-on-gray,#e2e4e7)!important;color:var(--heading-color);font-weight:700}.vnt-overtime-subgroup td{padding-left:20px;background-color:var(--subtle-accent,#f8f8f8)!important}
      .vnt-overtime-day{position:relative;display:flex;min-height:22px;align-items:center;justify-content:center;font-weight:700}.vnt-overtime-day.is-unreviewed{background:#fff2cc}.vnt-overtime-day.is-pending{background:#f59e0b}.vnt-overtime-day.is-approved{background:#c6e0b4}.vnt-overtime-day.is-approved_incomplete{background:#fce4d6}.vnt-overtime-day.is-rejected{background:#f4cccc}.vnt-overtime-badge{position:absolute;top:-7px;right:-6px;padding:0 3px;border-radius:7px;background:var(--card-bg,#fff);border:1px solid currentColor;font-size:8px;line-height:12px}.vnt-overtime-name-link{display:inline-flex;align-items:center;gap:4px;max-width:100%;color:inherit!important;font-weight:600;text-decoration:none!important}.vnt-overtime-name-link__text{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.vnt-overtime-name-link__icon{flex:0 0 auto;font-size:11px;opacity:0;transition:opacity .15s ease}.vnt-overtime-name-link:hover{color:var(--blue-500,#0289f7)!important;text-decoration:underline!important}.vnt-overtime-name-link:hover .vnt-overtime-name-link__icon{opacity:.85}.vnt-overtime-table tfoot td{background-color:var(--control-bg,#f4f5f6);color:var(--heading-color);font-weight:700}.vnt-overtime-empty{height:80px!important;color:var(--text-muted)}
      .vnt-overtime-legend{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 16px}.vnt-overtime-legend span{padding:5px 9px;border-radius:5px;font-size:11px}.vnt-overtime-legend .is-unreviewed{background:#fff2cc}.vnt-overtime-legend .is-pending{background:#f59e0b}.vnt-overtime-legend .is-approved{background:#c6e0b4}.vnt-overtime-legend .is-rejected{background:#f4cccc}.vnt-overtime-legend small{color:var(--text-muted)}@media print{.vnt-overtime-table-wrap{max-height:none;overflow:visible}.vnt-overtime-report{border:0}}
    `;
    document.head.appendChild(style);
  }

  function updateDateFilters(report) {
    const values = report.get_values() || {};
    const year = Number(values.year); const month = Number(values.month);
    if (!year || !month) return;
    report.set_filter_value("from_date", frappe.datetime.obj_to_str(new Date(year, month - 1, 1)));
    report.set_filter_value("to_date", frappe.datetime.obj_to_str(new Date(year, month, 0)));
  }

  const now = new Date();
  frappe.query_reports[REPORT_NAME] = {
    filters: [
      {fieldname:"company",label:"Công ty",fieldtype:"Link",options:"Company",reqd:1,default:frappe.defaults.get_user_default("Company")||frappe.defaults.get_global_default("company")},
      {fieldname:"month",label:"Tháng",fieldtype:"Select",options:"01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",reqd:1,default:String(now.getMonth()+1).padStart(2,"0"),on_change(){updateDateFilters(frappe.query_report);frappe.query_report.refresh();}},
      {fieldname:"year",label:"Năm",fieldtype:"Int",reqd:1,default:now.getFullYear(),on_change(){updateDateFilters(frappe.query_report);frappe.query_report.refresh();}},
      {fieldname:"department",label:"Phòng ban",fieldtype:"Link",options:"Department"},{fieldname:"branch",label:"Chi nhánh",fieldtype:"Link",options:"Branch"},{fieldname:"employee",label:"Nhân viên",fieldtype:"Link",options:"Employee"},{fieldname:"work_schedule_filter",label:"Loại ca/kíp",fieldtype:"Select",options:"\nCa Hành chính\nTheo kíp\nKíp đặc biệt"},{fieldname:"from_date",label:"Từ ngày",fieldtype:"Date",hidden:1},{fieldname:"to_date",label:"Đến ngày",fieldtype:"Date",hidden:1},
    ],
    onload(report) {
      installStyles(); updateDateFilters(report);
      const exportButton=report.page.add_inner_button("Tải xuống Excel",()=>{const query=new URLSearchParams({filters:JSON.stringify(report.get_filter_values(true))});window.open(frappe.urllib.get_full_url(`/api/method/${EXPORT_METHOD}?${query.toString()}`),"_blank");});exportButton.addClass("btn-primary");
      report.page.add_inner_button("Cập nhật giải trình",()=>{const values=report.get_filter_values(true);const yesterday=frappe.datetime.add_days(frappe.datetime.get_today(),-1);frappe.call({method:CONFIRM_METHOD,args:{from_date:values.from_date,to_date:values.to_date<yesterday?values.to_date:yesterday,company:values.company||null,department:values.department||null,branch:values.branch||null,employee:values.employee||null},freeze:true,freeze_message:__("Đang cập nhật giải trình tăng ca..."),callback(){report.refresh();}});});
    },
    after_datatable_render() {const report=frappe.query_report;report.$report.find(".datatable").attr("aria-hidden","true").hide();report.$report.find(".vnt-overtime-report").remove();report.$report.append(renderReport(report.data||[],report.get_filter_values()||{})).show();report.$report.off("click.vntOvertimeName").on("click.vntOvertimeName",".vnt-overtime-name-link",function(event){if(event.ctrlKey||event.metaKey||event.shiftKey||event.which===2){return;}event.preventDefault();const confirmDoc=this.getAttribute("data-confirm");if(confirmDoc){frappe.set_route("Form","VNT Attendance Confirm",confirmDoc);return;}const values=report.get_filter_values()||{};frappe.route_options={employee:this.getAttribute("data-employee")};if(values.month)frappe.route_options.month=values.month;if(values.year)frappe.route_options.year=values.year;frappe.set_route("List","VNT Attendance Confirm");});},
  };
})();

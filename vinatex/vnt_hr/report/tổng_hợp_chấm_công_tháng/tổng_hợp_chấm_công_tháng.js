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
      grid-template-columns: repeat(5, minmax(0, 1fr));
      align-items: stretch;
      gap: 10px;
      padding-bottom: 8px;
    }
    .vnt-attendance-legend__group {
      --legend-color: #64748b;
      --legend-soft: #f8fafc;
      --legend-border: #dbe3ec;
      display: flex;
      flex-direction: column;
      min-width: 0;
      height: 100%;
      padding: 12px 12px 10px;
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
      margin: 0 0 7px;
      padding-bottom: 7px;
      border-bottom: 1px solid var(--legend-border);
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
      grid-template-columns: 84px minmax(0, 1fr);
      align-items: start;
      gap: 8px;
      padding: 4px 0;
    }
    .vnt-attendance-legend__item + .vnt-attendance-legend__item {
      border-top: 1px dashed var(--border-color);
    }
    .vnt-attendance-legend__item.is-stacked {
      grid-template-columns: minmax(0, 1fr);
      gap: 4px;
    }
    .vnt-attendance-legend__item.is-stacked .vnt-attendance-legend__code {
      justify-self: start;
      white-space: nowrap;
    }
    .vnt-attendance-legend__code {
      display: inline-flex;
      min-height: 22px;
      align-items: center;
      justify-content: center;
      padding: 2px 6px;
      text-align: center;
      border: 1px solid var(--legend-border);
      border-radius: 7px;
      background: var(--legend-soft);
      color: var(--legend-color);
      font-size: 12px;
      font-weight: 700;
      line-height: 1.25;
      white-space: normal;
    }
    .vnt-attendance-legend__description {
      min-width: 0;
      color: var(--text-color);
      font-size: 12px;
      line-height: 1.35;
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
    @media (max-width: 1499px) {
      .vnt-attendance-legend__grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (max-width: 1099px) {
      .vnt-attendance-legend__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 767px) {
      .vnt-attendance-legend__grid { grid-template-columns: 1fr; }
      .vnt-attendance-legend__group { padding: 11px; }
      .vnt-attendance-legend__item { grid-template-columns: 82px minmax(0, 1fr); }
    }

    /* Bảng ma trận HTML thay cho datatable mặc định của Frappe. */
    .vnt-attendance-html-mode .report-wrapper { display: none !important; }
    .vnt-attendance-matrix-wrapper { margin-top: 2px; }
    .vnt-attendance-matrix-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 2px 7px;
      color: var(--text-muted);
      font-size: 12px;
    }
    .vnt-attendance-matrix-toolbar strong {
      color: var(--heading-color);
      font-weight: 600;
    }
    .vnt-attendance-matrix-search {
      width: 260px;
      max-width: 42vw;
      height: 28px;
      padding: 0 10px;
      border: 1px solid var(--border-color);
      border-radius: 7px;
      background: var(--card-bg);
      color: var(--text-color);
      font-size: 12px;
    }
    .vnt-attendance-matrix-search:focus {
      outline: none;
      border-color: var(--blue-500, #0289f7);
    }
    .vnt-attendance-matrix-hint { margin-left: auto; }
    .vnt-attendance-matrix-scroll {
      max-height: calc(100vh - 250px);
      overflow: auto;
      border: 1px solid var(--border-color);
      border-radius: 10px;
      background: var(--card-bg);
    }
    .vnt-attendance-matrix {
      width: max-content;
      min-width: 100%;
      table-layout: fixed;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 12px;
    }
    .vnt-attendance-matrix th,
    .vnt-attendance-matrix td {
      box-sizing: border-box;
      height: 30px;
      padding: 3px 8px;
      border-right: 1px solid var(--border-color);
      border-bottom: 1px solid var(--border-color);
      background-color: var(--card-bg, #fff);
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      vertical-align: middle;
    }
    .vnt-attendance-matrix thead th {
      position: sticky;
      top: 0;
      z-index: 3;
      height: 42px;
      padding: 3px 8px;
      background-color: var(--control-bg, #f4f5f6);
      color: var(--heading-color);
      font-size: 11px;
      font-weight: 600;
      text-align: left;
      text-transform: uppercase;
      letter-spacing: .02em;
    }
    .vnt-attendance-matrix th.is-frozen,
    .vnt-attendance-matrix td.is-frozen { position: sticky; z-index: 2; }
    .vnt-attendance-matrix thead th.is-frozen { z-index: 4; }
    .vnt-attendance-matrix th.is-last-frozen,
    .vnt-attendance-matrix td.is-last-frozen {
      box-shadow: 6px 0 8px -8px rgba(15, 23, 42, .45);
    }
    .vnt-attendance-matrix tbody tr:hover td { background-color: var(--subtle-fg, #f4f5f6); }
    .vnt-attendance-matrix th.is-day,
    .vnt-attendance-matrix td.is-day {
      padding: 2px 2px;
      text-align: center;
    }
    .vnt-attendance-matrix th.is-weekend {
      background-image: linear-gradient(rgba(249, 115, 22, .16), rgba(249, 115, 22, .16));
    }
    .vnt-attendance-matrix td.is-weekend {
      background-image: linear-gradient(rgba(249, 115, 22, .06), rgba(249, 115, 22, .06));
    }
    .vnt-attendance-matrix th.is-numeric,
    .vnt-attendance-matrix td.is-numeric {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    .vnt-attendance-matrix th.is-stt,
    .vnt-attendance-matrix td.is-stt {
      padding: 3px 4px;
      text-align: center;
      color: var(--text-muted);
    }
    .vnt-matrix__day { display: block; font-size: 12px; font-weight: 700; line-height: 1.15; }
    .vnt-matrix__weekday {
      display: block;
      font-size: 9.5px;
      font-weight: 500;
      line-height: 1.3;
      opacity: .72;
      text-transform: none;
    }
    .vnt-attendance-name-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      max-width: 100%;
      color: var(--text-color) !important;
      font-weight: 600;
      text-decoration: none !important;
    }
    .vnt-attendance-name-link__text {
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .vnt-attendance-name-link__icon {
      flex: 0 0 auto;
      font-size: 11px;
      opacity: 0;
      transition: opacity .15s ease;
    }
    .vnt-attendance-name-link:hover {
      color: var(--blue-500, #0289f7) !important;
      text-decoration: underline !important;
    }
    .vnt-attendance-name-link:hover .vnt-attendance-name-link__icon { opacity: .85; }
    .vnt-attendance-code-link {
      color: var(--text-muted) !important;
      font-variant-numeric: tabular-nums;
      text-decoration: none !important;
    }
    .vnt-attendance-code-link:hover { text-decoration: underline !important; }
    @media (max-width: 991px) {
      .vnt-attendance-matrix-scroll { max-height: calc(100vh - 200px); }
    }
  `;
}

// Install before the first report request/render. The onload call below remains
// as an idempotent fallback when Frappe restores a cached report instance.
installAttendanceLegendStyles();

function getSymbolColors(symbol) {
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
  return colors || ["#f5f5f5", "#424242"];
}

// Ô của một ngày: dùng chung cho bảng HTML và cho datatable (vẫn phục vụ
// Export/Print của Frappe dù datatable đã bị ẩn).
function renderAttendanceCell(value, data, fieldname) {
  if (isEmptyCellValue(value)) {
    return '<span style="display:block; width:100%; min-height:18px;">&nbsp;</span>';
  }
  const symbol = String(value || "");
  const colors = getSymbolColors(symbol);
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
  return `<span class="vnt-attendance-cell${state ? ` is-${state}` : ""}"${title} style="background:${colors[0]}; color:${colors[1]};"><span>${frappe.utils.escape_html(symbol)}</span>${badge}</span>`;
}

function stripAccents(text) {
  return String(text)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
}

// Khoá tìm kiếm giữ cả bản có dấu lẫn bản bỏ dấu để gõ kiểu nào cũng khớp.
function matrixSearchKey(row) {
  const joined = [row.employee_code, row.employee_name, row.department, row.shift_group]
    .filter((part) => part)
    .join(" ")
    .toLowerCase();
  return `${joined} ${stripAccents(joined)}`;
}

function isNumericColumn(column) {
  return ["Int", "Float", "Currency", "Percent"].includes(column && column.fieldtype);
}

function matrixColumnWidth(column) {
  const width = parseInt(column && column.width, 10);
  if (!isNaN(width) && width > 0) {
    return width;
  }
  return isDayColumn(column && column.fieldname) ? 58 : 120;
}

function getMatrixColumns(report) {
  return (report.columns || []).filter((column) => column && !column.hidden);
}

// Ngày đầu kỳ, dùng để suy ra thứ cho từng cột ngày.
function getMonthStart(report) {
  const values = (report && report.get_values && report.get_values()) || {};
  if (values.from_date) {
    const parsed = frappe.datetime.str_to_obj(values.from_date);
    if (parsed && !isNaN(parsed.getTime())) {
      return parsed;
    }
  }
  const year = parseInt(values.year, 10);
  const month = parseInt(values.month, 10);
  if (!isNaN(year) && !isNaN(month)) {
    return new Date(year, month - 1, 1);
  }
  return null;
}

function getDayWeekday(monthStart, fieldname) {
  if (!monthStart) {
    return null;
  }
  const day = parseInt(String(fieldname).slice(1), 10);
  if (isNaN(day)) {
    return null;
  }
  const date = new Date(monthStart.getFullYear(), monthStart.getMonth(), day);
  if (date.getMonth() !== monthStart.getMonth()) {
    return null;
  }
  return date.getDay();
}

function renderEmployeeNameCell(row) {
  const name = frappe.utils.escape_html(String(row.employee_name || ""));
  if (!row.employee) {
    return name;
  }
  const confirmDoc = row.confirm_document ? String(row.confirm_document) : "";
  const href = confirmDoc
    ? `/app/vnt-attendance-confirm/${encodeURIComponent(confirmDoc)}`
    : "/app/vnt-attendance-confirm";
  const hint = confirmDoc
    ? __("Mở phiếu giải trình {0}", [confirmDoc])
    : __("Mở danh sách giải trình đã lọc theo nhân viên và tháng");
  return (
    `<a class="vnt-attendance-name-link" href="${href}" title="${frappe.utils.escape_html(hint)}"` +
    ` data-employee="${frappe.utils.escape_html(String(row.employee))}"` +
    ` data-confirm="${frappe.utils.escape_html(confirmDoc)}">` +
    `<span class="vnt-attendance-name-link__text">${name}</span>` +
    `<span class="vnt-attendance-name-link__icon">→</span></a>`
  );
}

function renderMatrixCellValue(column, row) {
  const fieldname = column.fieldname;
  const value = row[fieldname];

  if (isDayColumn(fieldname)) {
    return renderAttendanceCell(value, row, fieldname);
  }
  if (fieldname === "employee_name") {
    return renderEmployeeNameCell(row);
  }
  if (fieldname === "employee_code") {
    const code = frappe.utils.escape_html(isEmptyCellValue(value) ? "" : String(value));
    if (!row.employee) {
      return code;
    }
    return `<a class="vnt-attendance-code-link" href="/app/employee/${encodeURIComponent(row.employee)}">${code}</a>`;
  }
  if (isEmptyCellValue(value)) {
    return "";
  }
  if (isNumericColumn(column)) {
    return frappe.format(value, column, { always_show_decimals: false }, row);
  }
  const text = frappe.utils.escape_html(String(value));
  return `<span title="${text}">${text}</span>`;
}

function buildMatrixHtml(report, columns) {
  const frozenFields = ["employee_code", "employee_name"];
  const weekdayLabels = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
  const sttWidth = 46;
  const rows = report.data || [];
  const monthStart = getMonthStart(report);

  // Chỉ ghim mã và tên nhân viên; cột STT cuộn theo bảng và chui xuống dưới.
  const frozenOffsets = {};
  let offset = 0;
  columns.forEach((column) => {
    if (frozenFields.includes(column.fieldname)) {
      frozenOffsets[column.fieldname] = offset;
      offset += matrixColumnWidth(column);
    }
  });
  const lastFrozen = columns
    .filter((column) => frozenOffsets[column.fieldname] !== undefined)
    .map((column) => column.fieldname)
    .pop();

  const classAttr = (classes) => (classes.length ? ` class="${classes.join(" ")}"` : "");
  const frozenAttrs = (fieldname) => {
    const classes = [];
    let style = "";
    if (frozenOffsets[fieldname] !== undefined) {
      classes.push("is-frozen");
      style = ` style="left:${frozenOffsets[fieldname]}px"`;
    }
    if (fieldname === lastFrozen) {
      classes.push("is-last-frozen");
    }
    return { classes, style };
  };

  const colTags = [`<col style="width:${sttWidth}px">`].concat(
    columns.map((column) => `<col style="width:${matrixColumnWidth(column)}px">`)
  );

  const headCells = [`<th class="is-stt">#</th>`].concat(
    columns.map((column) => {
      const { classes, style } = frozenAttrs(column.fieldname);
      const label = frappe.utils.escape_html(String(column.label || column.fieldname || ""));
      if (isDayColumn(column.fieldname)) {
        const weekday = getDayWeekday(monthStart, column.fieldname);
        classes.push("is-day");
        if (weekday === 0 || weekday === 6) {
          classes.push("is-weekend");
        }
        const weekdayLabel = weekday === null
          ? ""
          : `<span class="vnt-matrix__weekday">${weekdayLabels[weekday]}</span>`;
        return `<th${classAttr(classes)}${style}><span class="vnt-matrix__day">${label}</span>${weekdayLabel}</th>`;
      }
      if (isNumericColumn(column)) {
        classes.push("is-numeric");
      }
      return `<th${classAttr(classes)}${style} title="${label}">${label}</th>`;
    })
  );

  const bodyRows = rows.map((row, index) => {
    const cells = [`<td class="is-stt">${index + 1}</td>`].concat(
      columns.map((column) => {
        const { classes, style } = frozenAttrs(column.fieldname);
        if (isDayColumn(column.fieldname)) {
          const weekday = getDayWeekday(monthStart, column.fieldname);
          classes.push("is-day");
          if (weekday === 0 || weekday === 6) {
            classes.push("is-weekend");
          }
        } else if (isNumericColumn(column)) {
          classes.push("is-numeric");
        }
        return `<td${classAttr(classes)}${style}>${renderMatrixCellValue(column, row)}</td>`;
      })
    );
    return `<tr data-search="${frappe.utils.escape_html(matrixSearchKey(row))}">${cells.join("")}</tr>`;
  });

  return (
    `<div class="vnt-attendance-matrix-toolbar">` +
    `<input type="text" class="vnt-attendance-matrix-search" placeholder="${__("Tìm mã, tên, phòng ban, kíp...")}">` +
    `<span class="vnt-attendance-matrix-count"><strong>${rows.length}</strong> ${__("nhân viên")}</span>` +
    `<span class="vnt-attendance-matrix-hint">${__("Bấm tên nhân viên để mở giải trình chấm công của cả kỳ")}</span>` +
    `</div>` +
    `<div class="vnt-attendance-matrix-scroll">` +
    `<table class="vnt-attendance-matrix">` +
    `<colgroup>${colTags.join("")}</colgroup>` +
    `<thead><tr>${headCells.join("")}</tr></thead>` +
    `<tbody>${bodyRows.join("")}</tbody>` +
    `</table></div>`
  );
}

function bindMatrixEvents($container) {
  $container.on("click", ".vnt-attendance-name-link", function (event) {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.which === 2) {
      return; // Để trình duyệt tự mở tab mới theo href.
    }
    event.preventDefault();
    const confirmDoc = this.getAttribute("data-confirm");
    if (confirmDoc) {
      frappe.set_route("Form", "VNT Attendance Confirm", confirmDoc);
      return;
    }
    const values = (frappe.query_report && frappe.query_report.get_values()) || {};
    frappe.route_options = { employee: this.getAttribute("data-employee") };
    if (values.month) frappe.route_options.month = values.month;
    if (values.year) frappe.route_options.year = values.year;
    frappe.set_route("List", "VNT Attendance Confirm");
  });
}

function bindMatrixSearch($container) {
  $container.on("input", ".vnt-attendance-matrix-search", function () {
    const keyword = stripAccents(String(this.value || "").trim().toLowerCase());
    let shown = 0;
    $container.find("tbody tr").each(function () {
      const matched = !keyword || (this.getAttribute("data-search") || "").includes(keyword);
      this.style.display = matched ? "" : "none";
      if (matched) {
        shown += 1;
      }
    });
    $container.find(".vnt-attendance-matrix-count strong").text(shown);
  });
}

function getMatrixContainer(report) {
  if (report.$vnt_matrix && report.$vnt_matrix.closest("body").length) {
    return report.$vnt_matrix;
  }
  report.$vnt_matrix = $('<div class="vnt-attendance-matrix-wrapper" data-vnt-report-ui></div>').insertAfter(report.$report);
  bindMatrixEvents(report.$vnt_matrix);
  bindMatrixSearch(report.$vnt_matrix);
  return report.$vnt_matrix;
}

function clearAttendanceMatrix(report) {
  if (!report) {
    return;
  }
  if (report.page && report.page.main) {
    report.page.main.removeClass("vnt-attendance-html-mode");
  }
  if (report.$vnt_matrix) {
    report.$vnt_matrix.empty().hide();
  }
}

// Thay datatable bằng bảng HTML tự dựng. Datatable vẫn được Frappe tạo nhưng bị
// CSS ẩn đi, nhờ vậy Export/Print/Auto Email của báo cáo vẫn hoạt động.
function renderAttendanceMatrix(report) {
  if (!report || !report.$report) {
    return;
  }
  const columns = getMatrixColumns(report);
  const rows = report.data || [];
  if (!rows.length || !columns.some((column) => isDayColumn(column.fieldname))) {
    clearAttendanceMatrix(report);
    return;
  }
  installAttendanceLegendStyles();
  getMatrixContainer(report).html(buildMatrixHtml(report, columns)).show();
  report.page.main.addClass("vnt-attendance-html-mode");
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
    const fieldname = column && column.fieldname ? column.fieldname : "";

    if (!isDayColumn(fieldname)) {
      return default_formatter ? default_formatter(value, row, column, data) : value;
    }

    return renderAttendanceCell(value, data, fieldname);
  },

  after_datatable_render: function () {
    renderAttendanceMatrix(frappe.query_report);
  },

  onload: function (report) {
    installAttendanceLegendStyles();

    // after_datatable_render chỉ chạy khi truy vấn có dòng dữ liệu, nên phải tự
    // dọn bảng HTML cũ khi người dùng đổi bộ lọc hoặc bật báo cáo chi tiết.
    if (!report.__vnt_matrix_patched) {
      report.__vnt_matrix_patched = true;
      const original_refresh = report.refresh;
      report.refresh = function () {
        clearAttendanceMatrix(report);
        return original_refresh.apply(report, arguments);
      };
    }

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

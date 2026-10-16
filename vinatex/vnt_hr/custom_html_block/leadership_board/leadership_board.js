(() => {
  const dashboard = root_element.querySelector(".executive-dashboard");
  if (!dashboard) return;

  const BRANCHES_STORAGE_KEY = "vnt.hr.workspace.branches";
  const LEGACY_BRANCH_STORAGE_KEY = "vnt.hr.workspace.branch";
  const DATE_STORAGE_KEY = "vnt.hr.workspace.date";
  const today = frappe.datetime.get_today();
  const company = frappe.defaults.get_user_default("Company") || "";
  const formatter = new Intl.NumberFormat("vi-VN");
  const dateFormatter = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });

  const dateInput = dashboard.querySelector("[data-date-input]");
  const errorElement = dashboard.querySelector("[data-error]");
  const refreshButtons = dashboard.querySelectorAll("[data-refresh]");
  const host = root_element.host || root_element;

  const selectedBranches = [];
  let selectedDate = today;
  let requestSequence = 0;
  let pollHandle = null;
  let arrivalFilter = "all";
  let arrivalRows = [];

  try {
    window.sessionStorage.removeItem(BRANCHES_STORAGE_KEY);
    window.sessionStorage.removeItem(LEGACY_BRANCH_STORAGE_KEY);
    selectedDate = window.sessionStorage.getItem(DATE_STORAGE_KEY) || today;
  } catch (error) {
    selectedDate = window.__vntHrWorkspaceDate || today;
  }
  window.__vntHrWorkspaceBranches = [];
  window.__vntHrWorkspaceBranch = "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(selectedDate) || selectedDate > today) selectedDate = today;
  dateInput.max = today;
  dateInput.value = selectedDate;

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    })[character]);
  }

  function formatDate(value) {
    if (!value) return "";
    const parts = String(value).split("-").map(Number);
    if (parts.length !== 3 || parts.some((part) => !part)) return String(value);
    return dateFormatter.format(new Date(parts[0], parts[1] - 1, parts[2]));
  }

  function persistDate() {
    window.__vntHrWorkspaceDate = selectedDate;
    try {
      window.sessionStorage.setItem(DATE_STORAGE_KEY, selectedDate);
    } catch (error) {
      console.debug("Không thể lưu ngày theo dõi của bảng tin lãnh đạo", error);
    }
  }

  function showError(message) {
    errorElement.textContent = message || "Không thể tải bảng tin lãnh đạo. Vui lòng thử lại.";
    errorElement.hidden = false;
  }

  function setLoading(loading) {
    dashboard.classList.toggle("is-loading", loading);
    refreshButtons.forEach((button) => { button.disabled = loading; });
  }

  function kpiTitle(item, morning) {
    if (selectedDate === today) return item.title;
    const selectedLabel = formatDate(morning.as_of_date);
    const previousLabel = formatDate(morning.previous_date);
    const titles = {
      arrived_today: `Đã đến ngày ${selectedLabel}`,
      absent_yesterday: `Vắng ngày ${previousLabel}`,
      explanation_yesterday: `Cần giải trình ngày ${previousLabel}`,
      late_yesterday: `Đi muộn ngày ${previousLabel}`,
      early_yesterday: `Về sớm cần đối soát ngày ${previousLabel}`,
      birthdays_today: `Sinh nhật ngày ${selectedLabel}`
    };
    return titles[item.id] || item.title;
  }

  function renderKpis(items, morning) {
    const element = dashboard.querySelector("[data-kpis]");
    element.innerHTML = (items || []).map((item) => `
      <button type="button" class="executive-kpi executive-kpi--${escapeHtml(item.tone || "blue")}" data-target="${escapeHtml(item.target || "")}">
        <span class="executive-kpi__title">${escapeHtml(kpiTitle(item, morning))}</span>
        <strong class="executive-kpi__value">${formatter.format(Number(item.value) || 0)}</strong>
        <span class="executive-kpi__caption">${escapeHtml(item.caption || "")}</span>
      </button>
    `).join("");
  }

  function personMeta(row) {
    return [row.designation, row.department].filter(Boolean).join(" · ") || "Chưa cập nhật đơn vị";
  }

  function renderArrivalRows() {
    const filtered = arrivalFilter === "all"
      ? arrivalRows
      : arrivalRows.filter((row) => row.group === arrivalFilter);
    const body = dashboard.querySelector("[data-arrival-rows]");
    const empty = dashboard.querySelector("[data-arrival-empty]");
    body.innerHTML = filtered.map((row) => `
      <tr>
        <td>
          <div class="executive-person-name">${escapeHtml(row.employee_name)}</div>
          <span class="executive-role executive-role--${escapeHtml(row.group)}">${escapeHtml(row.group_label)}</span>
        </td>
        <td><span title="${escapeHtml(row.department)}">${escapeHtml(row.department || "—")}</span></td>
        <td>${escapeHtml(row.planned_shift || row.arrival_source || "Ngoài ca")}</td>
        <td><strong>${escapeHtml(row.first_in || "—")}</strong>${row.arrival_source === "Ngoài ca" ? '<small class="executive-outside">Ngoài ca</small>' : ""}</td>
      </tr>
    `).join("");
    empty.hidden = filtered.length > 0;
    dashboard.querySelector(".executive-table").hidden = filtered.length === 0;
  }

  function renderArrivals(data) {
    arrivalRows = [...(data.managers || []), ...(data.employees || [])];
    dashboard.querySelector("[data-arrival-total]").textContent = formatter.format(Number(data.total) || 0);
    dashboard.querySelector("[data-arrival-expected]").textContent = formatter.format(Number(data.expected) || 0);
    dashboard.querySelector("[data-arrival-all]").textContent = formatter.format(Number(data.total) || 0);
    dashboard.querySelector("[data-arrival-manager]").textContent = formatter.format(Number(data.manager_count) || 0);
    dashboard.querySelector("[data-arrival-employee]").textContent = formatter.format(Number(data.employee_count) || 0);
    renderArrivalRows();
  }

  function renderBirthdayGroup(selector, rows, emptyLabel) {
    const element = dashboard.querySelector(selector);
    if (!rows || !rows.length) {
      element.innerHTML = `<div class="executive-mini-empty">${escapeHtml(emptyLabel)}</div>`;
      return;
    }
    element.innerHTML = rows.map((row) => `
      <div class="executive-person-row">
        <span class="executive-avatar" aria-hidden="true">${escapeHtml((row.employee_name || "?").trim().charAt(0))}</span>
        <div><strong>${escapeHtml(row.employee_name)}</strong><small>${escapeHtml(personMeta(row))}</small></div>
      </div>
    `).join("");
  }

  function renderBirthdays(data) {
    dashboard.querySelector("[data-birthday-total]").textContent = formatter.format(Number(data.total) || 0);
    dashboard.querySelector("[data-birthday-manager-count]").textContent = formatter.format(Number(data.manager_count) || 0);
    dashboard.querySelector("[data-birthday-employee-count]").textContent = formatter.format(Number(data.employee_count) || 0);
    renderBirthdayGroup("[data-birthday-managers]", data.managers || [], "Không có sinh nhật quản lý hôm nay");
    renderBirthdayGroup("[data-birthday-employees]", data.employees || [], "Không có sinh nhật nhân viên hôm nay");
  }

  function issueRow(row, detail, metric, metricClass = "") {
    return `
      <div class="executive-issue-row">
        <div>
          <div class="executive-person-name">${escapeHtml(row.employee_name)}</div>
          <div class="executive-issue-meta"><span class="executive-role-dot ${row.group === "manager" ? "executive-role-dot--manager" : ""}"></span>${escapeHtml(detail || personMeta(row))}</div>
          ${row.outside_out_time ? `<div class="executive-issue-evidence">Có OUT ngoài ca ${escapeHtml(row.outside_out_time)} chưa được tính</div>` : ""}
        </div>
        <strong class="${escapeHtml(metricClass)}">${escapeHtml(metric || "")}</strong>
      </div>
    `;
  }

  function renderIssueList(selector, rows, detailBuilder, metricBuilder, emptyText) {
    const element = dashboard.querySelector(selector);
    if (!rows || !rows.length) {
      element.innerHTML = `<div class="executive-mini-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    element.innerHTML = rows.map((row) => issueRow(row, detailBuilder(row), metricBuilder(row))).join("");
  }

  function renderYesterday(data) {
    dashboard.querySelector("[data-yesterday-date]").textContent = `(${formatDate(data.date)})`;
    dashboard.querySelector("[data-scheduled-yesterday]").textContent = formatter.format(Number(data.scheduled) || 0);
    dashboard.querySelector("[data-absent-count]").textContent = formatter.format((data.absent || []).length);
    dashboard.querySelector("[data-absent-finalized]").textContent = formatter.format(Number(data.absent_finalized) || 0);
    dashboard.querySelector("[data-absent-provisional]").textContent = formatter.format(Number(data.absent_provisional) || 0);
    dashboard.querySelector("[data-explanation-count]").textContent = formatter.format((data.explanations || []).length);
    dashboard.querySelector("[data-awaiting-hr]").textContent = formatter.format((data.awaiting_hr || []).length);
    dashboard.querySelector("[data-late-count]").textContent = formatter.format((data.late || []).length);
    dashboard.querySelector("[data-late-average]").textContent = formatter.format(Number((data.late_summary || {}).average_minutes) || 0);
    dashboard.querySelector("[data-late-maximum]").textContent = formatter.format(Number((data.late_summary || {}).maximum_minutes) || 0);
    dashboard.querySelector("[data-early-count]").textContent = formatter.format((data.early || []).length);
    dashboard.querySelector("[data-early-average]").textContent = formatter.format(Number((data.early_summary || {}).average_minutes) || 0);
    dashboard.querySelector("[data-early-maximum]").textContent = formatter.format(Number((data.early_summary || {}).maximum_minutes) || 0);

    renderIssueList(
      "[data-absent-list]", data.absent || [],
      (row) => [row.department, row.planned_shift, row.source].filter(Boolean).join(" · "),
      (row) => row.finalized ? "Đã chốt" : "Tạm tính",
      "Không ghi nhận trường hợp vắng"
    );
    renderIssueList(
      "[data-explanation-list]", data.explanations || [],
      (row) => (row.issues || []).map((issue) => issue.issue_type).join(" · ") || personMeta(row),
      (row) => `${(row.issues || []).length} vấn đề`,
      "Không có trường hợp đang chờ giải trình"
    );
    renderIssueList(
      "[data-late-list]", data.late || [],
      (row) => `${row.department || "—"} · ${row.planned_shift || "—"} · ${row.planned_time || "—"} → ${row.actual_time || "—"}`,
      (row) => `+${formatter.format(Number(row.minutes) || 0)} phút`,
      "Không ghi nhận trường hợp đi muộn"
    );
    renderIssueList(
      "[data-early-list]", data.early || [],
      (row) => `${row.department || "—"} · ${row.planned_shift || "—"} · ${row.actual_time || "—"} / ${row.planned_time || "—"}`,
      (row) => `-${formatter.format(Number(row.minutes) || 0)} phút`,
      "Không ghi nhận trường hợp về sớm"
    );
  }

  function renderSnapshot(data) {
    const morning = data.morning || {};
    renderKpis(data.kpis || morning.kpis || [], morning);
    renderArrivals(morning.arrivals || {});
    renderBirthdays(morning.birthdays || {});
    renderYesterday(morning.yesterday || {});

    const selectedLabel = formatDate(morning.as_of_date);
    const previousLabel = formatDate(morning.previous_date);
    const isCurrentDay = selectedDate === today;
    dashboard.querySelector("#executive-arrivals-title").textContent = isCurrentDay
      ? "Ai đã đến công ty hôm nay?"
      : `Ai đã đến công ty ngày ${selectedLabel}?`;
    dashboard.querySelector("#executive-birthdays-title").textContent = isCurrentDay
      ? "Sinh nhật hôm nay"
      : `Sinh nhật ngày ${selectedLabel}`;
    dashboard.querySelector("[data-period-copy]").textContent = selectedDate === today
      ? `Hiện diện hôm nay ${selectedLabel} · đối soát hôm qua ${previousLabel}`
      : `Hiện diện ngày ${selectedLabel} · đối soát ngày ${previousLabel}`;
    const reportLink = dashboard.querySelector(".executive-link");
    reportLink.href = `/app/query-report/VNT%20Daily%20Attendance?from_date=${encodeURIComponent(morning.previous_date || "")}&to_date=${encodeURIComponent(morning.previous_date || "")}&company=${encodeURIComponent((data.scope || {}).company || "")}`;
    dashboard.querySelector("[data-scope-label]").textContent = (data.scope || {}).label || "Tất cả chi nhánh";
    dashboard.querySelector("[data-timezone]").textContent = (data.context || {}).timezone || "Asia/Ho_Chi_Minh";
    dashboard.querySelector("[data-manager-definition]").textContent = (data.context || {}).manager_definition || "";
    const generatedAt = (data.context || {}).generated_at;
    const latestCheckinAt = (data.context || {}).latest_checkin_at;
    dashboard.querySelector("[data-updated]").textContent = generatedAt
      ? `Tính lúc ${String(generatedAt).slice(11, 16)}${latestCheckinAt ? ` · log mới nhất ${String(latestCheckinAt).slice(11, 16)}` : ""}`
      : "Đã cập nhật";
  }

  async function load(force = false) {
    const sequence = ++requestSequence;
    errorElement.hidden = true;
    setLoading(true);
    try {
      const data = await frappe.xcall("vinatex.api.leadership_dashboard.get_leadership_snapshot", {
        as_of_date: selectedDate,
        branches: selectedBranches,
        company,
        force: force ? 1 : 0
      });
      if (sequence !== requestSequence) return;
      renderSnapshot(data || {});
    } catch (error) {
      if (sequence !== requestSequence) return;
      console.error("Không thể tải bảng tin lãnh đạo", error);
      showError(error && (error.message || error.exc_type)
        ? String(error.message || error.exc_type)
        : "Không thể tải bảng tin lãnh đạo. Vui lòng thử lại.");
    } finally {
      if (sequence === requestSequence) setLoading(false);
    }
  }

  dateInput.addEventListener("change", () => {
    selectedDate = dateInput.value || today;
    if (selectedDate > today) selectedDate = today;
    dateInput.value = selectedDate;
    persistDate();
    load(false);
  });
  refreshButtons.forEach((button) => button.addEventListener("click", () => load(true)));
  dashboard.querySelector("[data-kpis]").addEventListener("click", (event) => {
    const card = event.target.closest("[data-target]");
    const targetId = card && card.dataset.target;
    const target = targetId ? dashboard.querySelector(`#${targetId}`) : null;
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  dashboard.querySelector(".executive-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-arrival-filter]");
    if (!button) return;
    arrivalFilter = button.dataset.arrivalFilter;
    dashboard.querySelectorAll("[data-arrival-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
    renderArrivalRows();
  });

  const realtimeHandler = () => {
    if (host.isConnected) load(true);
  };
  if (frappe.realtime && frappe.realtime.on) frappe.realtime.on("leadership_dashboard_update", realtimeHandler);

  pollHandle = window.setInterval(() => {
    if (!host.isConnected) {
      window.clearInterval(pollHandle);
      if (frappe.realtime && frappe.realtime.off) frappe.realtime.off("leadership_dashboard_update", realtimeHandler);
      return;
    }
    if (!document.hidden && selectedDate === today) load(false);
  }, 60000);

  load();
})();

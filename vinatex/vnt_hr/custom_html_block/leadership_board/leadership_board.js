(() => {
  const dashboard = root_element.querySelector(".executive-dashboard");
  if (!dashboard) return;

  const BRANCHES_STORAGE_KEY = "vnt.hr.workspace.branches";
  const LEGACY_BRANCH_STORAGE_KEY = "vnt.hr.workspace.branch";
  const DATE_STORAGE_KEY = "vnt.hr.workspace.date";
  const today = frappe.datetime.get_today();
  const company = frappe.defaults.get_user_default("Company") || "";
  const formatter = new Intl.NumberFormat("vi-VN");
  const currencyFormatter = new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0
  });

  const dateInput = dashboard.querySelector("[data-date-input]");
  const picker = dashboard.querySelector("[data-branch-picker]");
  const trigger = dashboard.querySelector("[data-branch-trigger]");
  const summary = dashboard.querySelector("[data-branch-summary]");
  const menu = dashboard.querySelector("[data-branch-menu]");
  const allCheckbox = dashboard.querySelector("[data-all-branches]");
  const branchOptionsElement = dashboard.querySelector("[data-branch-options]");
  const clearButton = dashboard.querySelector("[data-clear]");
  const errorElement = dashboard.querySelector("[data-error]");
  const refreshButtons = dashboard.querySelectorAll("[data-refresh]");
  const host = root_element.host || root_element;

  let selectedBranches = [];
  let selectedDate = today;
  let branchNames = [];
  let activeRequest = null;
  let requestSequence = 0;
  let pollHandle = null;
  let turnoverChart = null;
  let salaryChart = null;

  try {
    const stored = window.sessionStorage.getItem(BRANCHES_STORAGE_KEY);
    const legacy = window.sessionStorage.getItem(LEGACY_BRANCH_STORAGE_KEY);
    const parsed = stored ? JSON.parse(stored) : [];
    selectedBranches = Array.isArray(parsed) ? parsed.map(String) : [];
    if (!selectedBranches.length && legacy) selectedBranches = [legacy];
    selectedDate = window.sessionStorage.getItem(DATE_STORAGE_KEY) || today;
  } catch (error) {
    selectedBranches = Array.isArray(window.__vntHrWorkspaceBranches)
      ? [...window.__vntHrWorkspaceBranches]
      : (window.__vntHrWorkspaceBranch ? [window.__vntHrWorkspaceBranch] : []);
    selectedDate = window.__vntHrWorkspaceDate || today;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(selectedDate) || selectedDate > today) selectedDate = today;
  dateInput.max = today;
  dateInput.value = selectedDate;

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    })[character]);
  }

  function closeMenu() {
    menu.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    picker.classList.remove("is-open");
  }

  function renderSelection() {
    const selectedSet = new Set(selectedBranches);
    allCheckbox.checked = selectedBranches.length === 0;
    branchOptionsElement.querySelectorAll("input[data-branch]").forEach((input) => {
      input.checked = selectedSet.has(input.value);
    });
    if (!selectedBranches.length) summary.textContent = "Tất cả chi nhánh";
    else if (selectedBranches.length === 1) summary.textContent = selectedBranches[0];
    else summary.textContent = `${selectedBranches.length} chi nhánh đã chọn`;
    clearButton.hidden = selectedBranches.length === 0;
  }

  function persistFilters() {
    window.__vntHrWorkspaceBranches = [...selectedBranches];
    window.__vntHrWorkspaceBranch = selectedBranches.length === 1 ? selectedBranches[0] : "";
    window.__vntHrWorkspaceDate = selectedDate;
    try {
      if (selectedBranches.length) {
        window.sessionStorage.setItem(BRANCHES_STORAGE_KEY, JSON.stringify(selectedBranches));
      } else {
        window.sessionStorage.removeItem(BRANCHES_STORAGE_KEY);
      }
      window.sessionStorage.removeItem(LEGACY_BRANCH_STORAGE_KEY);
      window.sessionStorage.setItem(DATE_STORAGE_KEY, selectedDate);
    } catch (error) {
      console.debug("Không thể lưu bộ lọc bảng tin lãnh đạo", error);
    }
    renderSelection();
  }

  function buildBranchOptions() {
    branchOptionsElement.textContent = "";
    branchNames.forEach((name) => {
      const label = document.createElement("label");
      label.className = "executive-filter__option";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = name;
      input.setAttribute("data-branch", "");
      const text = document.createElement("span");
      text.textContent = name;
      label.append(input, text);
      branchOptionsElement.appendChild(label);
    });
    renderSelection();
  }

  function showError(message) {
    errorElement.textContent = message || "Không thể tải bảng tin lãnh đạo. Vui lòng thử lại.";
    errorElement.hidden = false;
  }

  function setLoading(loading) {
    dashboard.classList.toggle("is-loading", loading);
    refreshButtons.forEach((button) => { button.disabled = loading; });
  }

  function formatKpiValue(item) {
    const value = Number(item.value) || 0;
    if (item.display_type === "signed") return `${value > 0 ? "+" : ""}${formatter.format(value)}`;
    return formatter.format(value);
  }

  function renderKpis(items) {
    const element = dashboard.querySelector("[data-kpis]");
    element.innerHTML = (items || []).map((item) => `
      <article class="executive-kpi executive-kpi--${escapeHtml(item.tone || "indigo")}">
        <div class="executive-kpi__title">${escapeHtml(item.title)}</div>
        <div class="executive-kpi__value">${escapeHtml(formatKpiValue(item))}</div>
        <div class="executive-kpi__caption">${escapeHtml(item.caption || "")}</div>
      </article>
    `).join("");
  }

  function renderAttention(items) {
    const element = dashboard.querySelector("[data-attention]");
    element.innerHTML = (items || []).map((item) => {
      const first = (item.items || [])[0];
      const preview = first
        ? `${first.label}${first.date ? ` · ${first.date}` : ""}`
        : (Number(item.value) ? "Mở danh sách để xem chi tiết" : "Không có nội dung cần xử lý");
      return `
        <button type="button" class="executive-attention-card executive-attention-card--${escapeHtml(item.tone || "blue")}" data-route="${escapeHtml(item.route || "")}">
          <div class="executive-attention-card__top">
            <span class="executive-attention-card__title">${escapeHtml(item.title)}</span>
            <i class="fa fa-arrow-right executive-attention-card__arrow" aria-hidden="true"></i>
          </div>
          <div class="executive-attention-card__value">${formatter.format(Number(item.value) || 0)}</div>
          <div class="executive-attention-card__caption">${escapeHtml(item.caption || "")}</div>
          <div class="executive-attention-card__preview" title="${escapeHtml(preview)}">${escapeHtml(preview)}</div>
        </button>
      `;
    }).join("");
  }

  function renderAttendance(data) {
    const rows = [
      { label: "Có mặt", value: data.present, color: "#10b981" },
      { label: "Nghỉ phép", value: data.leave, color: "#ec4899" },
      { label: "Công tác", value: data.trip, color: "#3b82f6" },
      { label: "Chưa ghi nhận", value: data.unrecorded, color: "#94a3b8" }
    ];
    const total = Number(data.total) || 0;
    dashboard.querySelector("[data-coverage]").textContent = Number(data.coverage_rate || 0).toLocaleString("vi-VN");
    dashboard.querySelector("[data-attendance]").innerHTML = rows.map((row) => {
      const percentage = total ? Math.round((Number(row.value) || 0) / total * 100) : 0;
      return `
        <div class="executive-status-row">
          <span class="executive-status-row__label">${escapeHtml(row.label)}</span>
          <div class="executive-status-row__track" aria-hidden="true">
            <div class="executive-status-row__bar" style="width:${percentage}%;background:${row.color}"></div>
          </div>
          <span class="executive-status-row__value">${formatter.format(Number(row.value) || 0)}<small>${percentage}%</small></span>
        </div>
      `;
    }).join("");
  }

  function renderBranches(rows) {
    const element = dashboard.querySelector("[data-branches]");
    dashboard.querySelector("[data-branch-count]").textContent = formatter.format((rows || []).length);
    if (!rows || !rows.length) {
      element.innerHTML = '<div class="executive-state">Chưa có dữ liệu chi nhánh.</div>';
      return;
    }
    const colors = ["#4f46e5", "#3b82f6", "#14b8a6", "#f59e0b", "#8b5cf6", "#ec4899"];
    const maxValue = Math.max(...rows.map((row) => Number(row.value) || 0), 1);
    element.innerHTML = rows.map((row, index) => `
      <div class="executive-branch-row">
        <span class="executive-branch-row__label" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span>
        <div class="executive-branch-row__track" aria-hidden="true">
          <div class="executive-branch-row__bar" style="width:${Math.round((Number(row.value) || 0) / maxValue * 100)}%;background:${colors[index % colors.length]}"></div>
        </div>
        <span class="executive-branch-row__value">${formatter.format(Number(row.value) || 0)}<small>${Number(row.percentage || 0).toLocaleString("vi-VN")}%</small></span>
      </div>
    `).join("");
  }

  function renderLeaders(rows) {
    const element = dashboard.querySelector("[data-leaders]");
    dashboard.querySelector("[data-leader-count]").textContent = formatter.format((rows || []).length);
    if (!rows || !rows.length) {
      element.innerHTML = '<div class="executive-state">Chưa có dữ liệu lãnh đạo và quản lý trong phạm vi đã chọn.</div>';
      return;
    }
    element.innerHTML = rows.map((row) => {
      const meta = [row.designation, row.department, row.detail].filter(Boolean).join(" · ");
      return `
        <div class="executive-leader-row">
          <div>
            <div class="executive-leader-row__name" title="${escapeHtml(row.employee_name)}">${escapeHtml(row.employee_name)}</div>
            <div class="executive-leader-row__meta" title="${escapeHtml(meta)}">${escapeHtml(meta || "Chưa cập nhật chức danh")}</div>
          </div>
          <span class="executive-status-chip executive-status-chip--${escapeHtml(row.status)}">${escapeHtml(row.status_label)}</span>
        </div>
      `;
    }).join("");
  }

  function renderTurnover(data) {
    const chartElement = dashboard.querySelector("[data-turnover-chart]");
    const stateElement = dashboard.querySelector("[data-turnover-state]");
    const summaryData = data.summary || {};
    dashboard.querySelector("[data-hiring-total]").textContent = formatter.format(Number(summaryData.hiring) || 0);
    dashboard.querySelector("[data-attrition-total]").textContent = formatter.format(Number(summaryData.attrition) || 0);

    if (!data.labels || !data.labels.length || typeof frappe.Chart !== "function") {
      if (turnoverChart && typeof turnoverChart.destroy === "function") turnoverChart.destroy();
      turnoverChart = null;
      chartElement.hidden = true;
      stateElement.hidden = false;
      stateElement.textContent = data.labels && data.labels.length
        ? "Thư viện biểu đồ chưa sẵn sàng."
        : "Chưa có dữ liệu biến động nhân sự.";
      return;
    }
    if (turnoverChart && typeof turnoverChart.destroy === "function") turnoverChart.destroy();
    chartElement.textContent = "";
    chartElement.hidden = false;
    stateElement.hidden = true;
    turnoverChart = new frappe.Chart(chartElement, {
      data: { labels: data.labels, datasets: data.datasets || [] },
      type: "line",
      height: 228,
      colors: ["#60a5fa", "#8b5cf6"],
      axisOptions: { xAxisMode: "tick", yAxisMode: "span", xIsSeries: 1 },
      lineOptions: { regionFill: 1, hideDots: 0, dotSize: 4 },
      tooltipOptions: { formatTooltipY: (value) => formatter.format(value) + " nhân sự" },
      animate: 1
    });
  }

  function renderFinance(finance) {
    const stateElement = dashboard.querySelector("[data-finance-state]");
    const contentElement = dashboard.querySelector("[data-finance-content]");
    const kpisElement = dashboard.querySelector("[data-finance-kpis]");
    const chartElement = dashboard.querySelector("[data-salary-chart]");

    if (!finance.available || !finance.has_data) {
      if (salaryChart && typeof salaryChart.destroy === "function") salaryChart.destroy();
      salaryChart = null;
      contentElement.hidden = true;
      stateElement.hidden = false;
      stateElement.classList.toggle("is-restricted", !finance.available);
      stateElement.textContent = finance.message || "Chưa có dữ liệu bảng lương.";
      return;
    }

    stateElement.hidden = true;
    contentElement.hidden = false;
    kpisElement.innerHTML = (finance.kpis || []).map((item) => `
      <article class="executive-finance-card">
        <div class="executive-finance-card__title">${escapeHtml(item.title)}</div>
        <div class="executive-finance-card__value">${escapeHtml(currencyFormatter.format(Number(item.value) || 0))}</div>
        <div class="executive-finance-card__caption">${escapeHtml(item.caption || "")}</div>
      </article>
    `).join("");

    const chart = finance.chart || {};
    if (!chart.labels || !chart.labels.length || typeof frappe.Chart !== "function") {
      if (salaryChart && typeof salaryChart.destroy === "function") salaryChart.destroy();
      salaryChart = null;
      chartElement.innerHTML = '<div class="executive-state">Chưa có dữ liệu biểu đồ lương.</div>';
      return;
    }
    if (salaryChart && typeof salaryChart.destroy === "function") salaryChart.destroy();
    chartElement.textContent = "";
    salaryChart = new frappe.Chart(chartElement, {
      data: { labels: chart.labels, datasets: chart.datasets || [] },
      type: "line",
      height: 242,
      colors: ["#4f46e5", "#10b981"],
      axisOptions: { xAxisMode: "tick", yAxisMode: "span", xIsSeries: 1 },
      lineOptions: { regionFill: 0, hideDots: 0, dotSize: 4 },
      tooltipOptions: { formatTooltipY: (value) => currencyFormatter.format(value) },
      animate: 1
    });
  }

  function renderSnapshot(data) {
    renderKpis(data.kpis || []);
    renderAttention(data.attention || []);
    renderAttendance(data.attendance || {});
    renderBranches(data.branches || []);
    renderLeaders((data.attendance || {}).leaders || []);
    renderTurnover(data.turnover || {});
    renderFinance(data.finance || {});

    const scope = data.scope || {};
    dashboard.querySelector("[data-scope-label]").textContent = scope.label || "Tất cả chi nhánh";
    const generatedAt = (data.context || {}).generated_at;
    dashboard.querySelector("[data-updated]").textContent = generatedAt
      ? `Cập nhật ${String(generatedAt).slice(11, 16)}`
      : "Đã cập nhật";
  }

  async function load(force = false) {
    const sequence = ++requestSequence;
    errorElement.hidden = true;
    setLoading(true);
    const request = frappe.xcall("vinatex.api.leadership_dashboard.get_leadership_snapshot", {
      as_of_date: selectedDate,
      branches: selectedBranches,
      company,
      force: force ? 1 : 0
    });
    activeRequest = request;
    try {
      const data = await request;
      if (sequence !== requestSequence) return;
      renderSnapshot(data || {});
    } catch (error) {
      if (sequence !== requestSequence) return;
      console.error("Không thể tải bảng tin lãnh đạo", error);
      const message = error && (error.message || error.exc_type)
        ? String(error.message || error.exc_type)
        : "Không thể tải bảng tin lãnh đạo. Vui lòng thử lại.";
      showError(message);
    } finally {
      if (sequence === requestSequence) {
        activeRequest = null;
        setLoading(false);
      }
    }
  }

  async function loadBranches() {
    trigger.disabled = true;
    summary.textContent = "Đang tải danh sách…";
    try {
      const rows = await frappe.xcall("vinatex.api.hr_dashboard.get_employee_branches", { company });
      branchNames = (Array.isArray(rows) ? rows : []).map(String).filter(Boolean);
      const validNames = new Set(branchNames);
      selectedBranches = selectedBranches.filter((name) => validNames.has(name));
      buildBranchOptions();
      persistFilters();
      await load();
    } catch (error) {
      console.error("Không thể tải danh sách chi nhánh", error);
      summary.textContent = "Không thể tải danh sách";
      showError("Không thể tải phạm vi chi nhánh được phép xem.");
    } finally {
      trigger.disabled = false;
    }
  }

  function applyFilters() {
    persistFilters();
    closeMenu();
    load(false);
  }

  trigger.addEventListener("click", () => {
    if (menu.hidden) {
      menu.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      picker.classList.add("is-open");
    } else closeMenu();
  });
  allCheckbox.addEventListener("change", () => { selectedBranches = []; applyFilters(); });
  branchOptionsElement.addEventListener("change", (event) => {
    const input = event.target.closest("input[data-branch]");
    if (!input) return;
    const selectedSet = new Set(selectedBranches);
    if (input.checked) selectedSet.add(input.value); else selectedSet.delete(input.value);
    selectedBranches = branchNames.filter((name) => selectedSet.has(name));
    applyFilters();
  });
  dateInput.addEventListener("change", () => {
    selectedDate = dateInput.value || today;
    if (selectedDate > today) selectedDate = today;
    dateInput.value = selectedDate;
    applyFilters();
  });
  clearButton.addEventListener("click", () => {
    selectedBranches = [];
    applyFilters();
    trigger.focus();
  });
  refreshButtons.forEach((button) => button.addEventListener("click", () => load(true)));
  dashboard.querySelector("[data-attention]").addEventListener("click", (event) => {
    const button = event.target.closest("[data-route]");
    const route = button && button.dataset.route;
    if (!route) return;
    const path = route.replace(/^\/app\/?/, "");
    frappe.set_route(...path.split("/").map((part) => decodeURIComponent(part)));
  });

  const outsideClickHandler = (event) => {
    if (!host.isConnected) {
      document.removeEventListener("click", outsideClickHandler, true);
      return;
    }
    if (!event.composedPath().includes(host)) closeMenu();
  };
  document.addEventListener("click", outsideClickHandler, true);
  root_element.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { closeMenu(); trigger.focus(); }
  });

  const realtimeHandler = () => {
    if (!host.isConnected) return;
    load(true);
  };
  if (frappe.realtime && frappe.realtime.on) {
    frappe.realtime.on("leadership_dashboard_update", realtimeHandler);
  }

  pollHandle = window.setInterval(() => {
    if (!host.isConnected) {
      window.clearInterval(pollHandle);
      document.removeEventListener("click", outsideClickHandler, true);
      if (turnoverChart && typeof turnoverChart.destroy === "function") turnoverChart.destroy();
      if (salaryChart && typeof salaryChart.destroy === "function") salaryChart.destroy();
      if (frappe.realtime && frappe.realtime.off) {
        frappe.realtime.off("leadership_dashboard_update", realtimeHandler);
      }
      return;
    }
    if (!document.hidden && selectedDate === today) load(false);
  }, 60000);

  loadBranches();
})();

(() => {
  const COLORS = ["#2563eb", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6", "#ef4444", "#84cc16", "#06b6d4"];
  const card = root_element.querySelector(".department-structure");
  if (!card) return;

  const body = card.querySelector("[data-body]");
  const listElement = card.querySelector("[data-list]");
  const stateElement = card.querySelector("[data-state]");
  const totalElement = card.querySelector("[data-total]");
  const refreshButton = card.querySelector(".department-structure__refresh");
  const formatter = new Intl.NumberFormat("vi-VN");
  let selectedBranches = Array.isArray(window.__vntHrWorkspaceBranches)
    ? [...window.__vntHrWorkspaceBranches]
    : (window.__vntHrWorkspaceBranch ? [window.__vntHrWorkspaceBranch] : []);
  let selectedDate = window.__vntHrWorkspaceDate || frappe.datetime.get_today();

  function showState(message, isError) {
    stateElement.textContent = message;
    stateElement.classList.toggle("is-error", Boolean(isError));
    stateElement.hidden = false;
    body.hidden = true;
  }

  function render(data) {
    const labels = Array.isArray(data && data.labels) ? data.labels : [];
    const datasets = Array.isArray(data && data.datasets) ? data.datasets : [];
    const values = datasets[0] && Array.isArray(datasets[0].values) ? datasets[0].values : [];
    const items = labels
      .map((label, index) => ({ label: String(label || "Chưa xác định"), value: Number(values[index]) || 0 }))
      .filter((item) => item.value > 0)
      .sort((left, right) => right.value - left.value || left.label.localeCompare(right.label, "vi"));

    if (!items.length) {
      totalElement.textContent = "0";
      showState("Chưa có dữ liệu phòng/bộ phận để hiển thị.", false);
      return;
    }

    const total = items.reduce((sum, item) => sum + item.value, 0);
    const maximum = Math.max(...items.map((item) => item.value), 1);
    totalElement.textContent = formatter.format(total);
    listElement.textContent = "";

    items.forEach((item, index) => {
      const percentage = total ? Math.round(item.value / total * 100) : 0;
      const relativeWidth = Math.max(item.value / maximum * 100, 1.5);
      const color = COLORS[index % COLORS.length];
      const description = `${item.label}: ${formatter.format(item.value)} NLĐ (${percentage}%)`;

      const row = document.createElement("div");
      row.className = "department-structure__row";
      row.setAttribute("role", "listitem");
      row.setAttribute("aria-label", description);
      row.title = description;
      row.style.animationDelay = `${index * 45}ms`;

      const header = document.createElement("div");
      header.className = "department-structure__row-header";
      const label = document.createElement("span");
      label.className = "department-structure__label";
      label.textContent = item.label;
      const value = document.createElement("span");
      value.className = "department-structure__value";
      value.textContent = formatter.format(item.value);
      const share = document.createElement("small");
      share.textContent = `${percentage}%`;
      value.appendChild(share);
      header.append(label, value);

      const track = document.createElement("div");
      track.className = "department-structure__track";
      const bar = document.createElement("div");
      bar.className = "department-structure__bar";
      bar.style.width = `${relativeWidth}%`;
      bar.style.background = color;
      bar.style.animationDelay = `${index * 45 + 80}ms`;
      track.appendChild(bar);

      row.append(header, track);
      listElement.appendChild(row);
    });

    body.hidden = false;
    stateElement.hidden = true;
  }

  async function getSnapshot() {
    const company = frappe.defaults.get_user_default("Company") || "";
    const key = [selectedDate, selectedBranches.join("\u001f"), company].join("|");
    const cache = window.__vntHrSnapshotCache || (window.__vntHrSnapshotCache = {});
    const cached = cache[key];
    if (cached && Date.now() - cached.createdAt < 2000) return cached.promise;
    const promise = frappe.xcall("vinatex.api.hr_dashboard.get_hr_dashboard_snapshot", {
      as_of_date: selectedDate,
      branches: selectedBranches,
      company
    });
    cache[key] = { createdAt: Date.now(), promise };
    try { return await promise; }
    catch (error) { delete cache[key]; throw error; }
  }

  async function load() {
    refreshButton.disabled = true;
    showState("Đang tải dữ liệu…", false);
    try {
      const response = await getSnapshot();
      render(response && response.dimensions ? response.dimensions.department : null);
    } catch (error) {
      console.error("Không thể tải cơ cấu người lao động theo phòng/bộ phận", error);
      showState("Không thể tải dữ liệu. Vui lòng thử lại.", true);
    } finally {
      refreshButton.disabled = false;
    }
  }

  const eventName = "vnt-hr-filter-change";
  if (root_element.__vntHrDepartmentFilterHandler) {
    document.removeEventListener(eventName, root_element.__vntHrDepartmentFilterHandler);
  }
  const filterHandler = (event) => {
    if (!root_element.isConnected) {
      document.removeEventListener(eventName, filterHandler);
      return;
    }
    const detail = (event && event.detail) || {};
    const nextBranches = Array.isArray(detail.branches)
      ? detail.branches.map(String)
      : (detail.branch ? [String(detail.branch)] : []);
    const nextDate = String(detail.as_of_date || frappe.datetime.get_today());
    if (JSON.stringify(nextBranches) === JSON.stringify(selectedBranches) && nextDate === selectedDate) return;
    selectedBranches = nextBranches;
    selectedDate = nextDate;
    load();
  };
  root_element.__vntHrDepartmentFilterHandler = filterHandler;
  document.addEventListener(eventName, filterHandler);
  refreshButton.addEventListener("click", load);
  load();
})();

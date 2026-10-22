(() => {
  const COLORS = ["#2563eb", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6", "#ef4444", "#84cc16", "#06b6d4"];
  const SVG_NS = "http://www.w3.org/2000/svg";
  const card = root_element.querySelector(".designation-group-donut");
  if (!card) return;

  const body = card.querySelector("[data-body]");
  const arcsElement = card.querySelector("[data-arcs]");
  const legendElement = card.querySelector("[data-legend]");
  const stateElement = card.querySelector("[data-state]");
  const totalElement = card.querySelector("[data-total]");
  const centerTotalElement = card.querySelector("[data-center-total]");
  const refreshButton = card.querySelector(".designation-group-donut__refresh");
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

  function setActive(index, active) {
    const arc = arcsElement.querySelector(`[data-index="${index}"]`);
    const row = legendElement.querySelector(`[data-index="${index}"]`);
    if (arc) arc.classList.toggle("is-active", active);
    if (row) row.classList.toggle("is-active", active);
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
      centerTotalElement.textContent = "0";
      showState("Chưa có dữ liệu nhóm chức danh để hiển thị.", false);
      return;
    }

    const total = items.reduce((sum, item) => sum + item.value, 0);
    let offset = 0;
    arcsElement.textContent = "";
    legendElement.textContent = "";
    totalElement.textContent = formatter.format(total);
    centerTotalElement.textContent = formatter.format(total);

    items.forEach((item, index) => {
      const exactPercentage = total ? item.value / total * 100 : 0;
      const percentage = Math.round(exactPercentage);
      const color = COLORS[index % COLORS.length];
      const description = `${item.label}: ${formatter.format(item.value)} NLĐ (${percentage}%)`;

      const circle = document.createElementNS(SVG_NS, "circle");
      circle.setAttribute("class", "designation-group-donut__arc");
      circle.setAttribute("cx", "110");
      circle.setAttribute("cy", "110");
      circle.setAttribute("r", "74");
      circle.setAttribute("pathLength", "100");
      circle.setAttribute("stroke", color);
      circle.setAttribute("stroke-dasharray", `${exactPercentage} ${100 - exactPercentage}`);
      circle.setAttribute("stroke-dashoffset", String(-offset));
      circle.setAttribute("data-index", String(index));
      circle.style.animationDelay = `${index * 70}ms`;
      const title = document.createElementNS(SVG_NS, "title");
      title.textContent = description;
      circle.appendChild(title);
      arcsElement.appendChild(circle);

      const row = document.createElement("div");
      row.className = "designation-group-donut__legend-row";
      row.setAttribute("role", "listitem");
      row.setAttribute("data-index", String(index));
      row.title = description;

      const dot = document.createElement("span");
      dot.className = "designation-group-donut__dot";
      dot.style.background = color;
      const label = document.createElement("span");
      label.className = "designation-group-donut__legend-label";
      label.textContent = item.label;
      const value = document.createElement("span");
      value.className = "designation-group-donut__legend-value";
      value.textContent = formatter.format(item.value);
      const share = document.createElement("small");
      share.textContent = `${percentage}%`;
      value.appendChild(share);

      row.append(dot, label, value);
      legendElement.appendChild(row);
      circle.addEventListener("mouseenter", () => setActive(index, true));
      circle.addEventListener("mouseleave", () => setActive(index, false));
      row.addEventListener("mouseenter", () => setActive(index, true));
      row.addEventListener("mouseleave", () => setActive(index, false));
      offset += exactPercentage;
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
      render(response && response.dimensions ? response.dimensions.designation_group : null);
    } catch (error) {
      console.error("Không thể tải cơ cấu người lao động theo nhóm chức danh", error);
      showState("Không thể tải dữ liệu. Vui lòng thử lại.", true);
    } finally {
      refreshButton.disabled = false;
    }
  }

  const eventName = "vnt-hr-filter-change";
  if (root_element.__vntHrDesignationGroupFilterHandler) {
    document.removeEventListener(eventName, root_element.__vntHrDesignationGroupFilterHandler);
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
  root_element.__vntHrDesignationGroupFilterHandler = filterHandler;
  document.addEventListener(eventName, filterHandler);
  refreshButton.addEventListener("click", load);
  load();
})();

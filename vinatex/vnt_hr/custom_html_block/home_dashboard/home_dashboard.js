(() => {
	"use strict";

	const root = root_element;
	const home = root.querySelector(".vnt-home");
	if (!home || root.__vntHomeMounted) return;
	root.__vntHomeMounted = true;

	const numberFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
	const calendarState = {
		year: new Date().getFullYear(),
		month: new Date().getMonth() + 1,
		tab: "common",
		data: { common: {}, personal: {} },
		requestId: 0,
	};

	const KPI_CONFIG = [
		{
			key: "work_days",
			report: "Ngày công trong tháng đến hôm nay",
			fieldname: "value",
			monthFilters: true,
			extra: { count_wfh: 1 },
		},
		{
			key: "leave_days",
			report: "Số ngày công tác và nghỉ phép trong tháng",
			fieldname: "value",
			monthFilters: true,
		},
		{
			key: "abnormal_days",
			report: "Số ngày chấm công bất thường",
			fieldname: "value",
			monthFilters: true,
			extra: { to_today: 1 },
		},
		{
			key: "remaining_leave",
			fieldname: "remaining",
			method: "vinatex.api.leave_kpi.get_my_remaining_annual_leave",
			extra: { leave_type: "Nghỉ phép năm" },
		},
	];

	function escapeHtml(value) {
		return String(value == null ? "" : value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function monthWindow() {
		const now = new Date();
		const year = now.getFullYear();
		const month = now.getMonth() + 1;
		const pad = (value) => String(value).padStart(2, "0");
		const lastDay = new Date(year, month, 0).getDate();
		return {
			year,
			month,
			from_date: `${year}-${pad(month)}-01`,
			to_date: `${year}-${pad(month)}-${pad(lastDay)}`,
		};
	}

	function reportUrl(name, filters) {
		const query = new URLSearchParams();
		Object.entries(filters || {}).forEach(([key, value]) => {
			if (value !== "" && value != null) query.set(key, value);
		});
		const suffix = query.toString() ? `?${query.toString()}` : "";
		return `/app/query-report/${encodeURIComponent(name)}${suffix}`;
	}

	function go(url) {
		if (!url) return;
		window.location.href = url;
	}

	function showAlert(message, indicator = "orange") {
		if (frappe.show_alert) frappe.show_alert({ message, indicator });
	}

	async function reportValue(config, filters) {
		if (config.method) {
			const result = await frappe.xcall(config.method, config.extra || {});
			return result && result[config.fieldname] != null ? result[config.fieldname] : 0;
		}

		const reportFilters = Object.assign(
			{},
			config.monthFilters ? filters : {},
			config.extra || {}
		);
		const result = await frappe.xcall("frappe.desk.query_report.run", {
			report_name: config.report,
			filters: reportFilters,
			ignore_prepared_report: 1,
		});
		const row = result && result.result && result.result.length ? result.result[0] : null;
		return row && row[config.fieldname] != null ? row[config.fieldname] : 0;
	}

	async function loadKpis() {
		const filters = monthWindow();
		home.querySelectorAll(".vnt-home__kpi").forEach((card) => card.classList.add("is-loading"));

		const results = await Promise.all(
			KPI_CONFIG.map(async (config) => {
				try {
					return { key: config.key, value: await reportValue(config, filters) };
				} catch (error) {
					console.error(`Không thể tải KPI ${config.key}`, error);
					return { key: config.key, value: 0 };
				}
			})
		);

		results.forEach(({ key, value }) => {
			const element = home.querySelector(`[data-kpi-key="${key}"] [data-kpi-value]`);
			if (element) element.textContent = numberFormatter.format(Number(value) || 0);
		});
		home.querySelectorAll(".vnt-home__kpi").forEach((card) => card.classList.remove("is-loading"));
	}

	function timeAgo(value) {
		if (!value) return "";
		const date = new Date(value);
		if (Number.isNaN(date.getTime())) return "";
		const days = Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
		if (days === 0) return "Hôm nay";
		if (days === 1) return "1 ngày trước";
		if (days < 7) return `${days} ngày trước`;
		if (days < 35) return `${Math.floor(days / 7)} tuần trước`;
		return `${Math.floor(days / 30)} tháng trước`;
	}

	function setFeedEmpty(type, message) {
		const list = home.querySelector(`[data-${type}-list]`);
		const empty = home.querySelector(`[data-${type}-empty]`);
		if (list) list.textContent = "";
		if (empty) {
			empty.textContent = message;
			empty.hidden = false;
		}
	}

	function renderTodos(items) {
		const list = home.querySelector("[data-todo-list]");
		const empty = home.querySelector("[data-todo-empty]");
		list.textContent = "";
		if (!items.length) {
			setFeedEmpty("todo", "Không có công việc cần thực hiện.");
			return;
		}
		empty.hidden = true;

		items.forEach((todo) => {
			const button = document.createElement("button");
			button.type = "button";
			button.className = "vnt-home__feed-item";
			button.innerHTML = `
				<span class="vnt-home__feed-copy">
					<span class="vnt-home__feed-title">${escapeHtml(todo.description || "Không có mô tả")}</span>
					<span class="vnt-home__feed-meta">${escapeHtml(todo.time_ago || "")}</span>
				</span>
				<span class="vnt-home__feed-state">${String(todo.status || "").toLowerCase() === "closed" ? "Đã đóng" : "Đang mở"}</span>`;
			button.addEventListener("click", () => {
				if (todo.reference_type && todo.reference_name) {
					frappe.set_route("Form", todo.reference_type, todo.reference_name);
				} else {
					frappe.set_route("Form", "ToDo", todo.name);
				}
			});
			list.appendChild(button);
		});
	}

	function renderNews(items) {
		const list = home.querySelector("[data-news-list]");
		const empty = home.querySelector("[data-news-empty]");
		list.textContent = "";
		if (!items.length) {
			setFeedEmpty("news", "Không có bản tin nào.");
			return;
		}
		empty.hidden = true;

		items.forEach((item) => {
			const button = document.createElement("button");
			button.type = "button";
			button.className = "vnt-home__feed-item";
			button.innerHTML = `
				<span class="vnt-home__feed-copy">
					<span class="vnt-home__feed-title">${escapeHtml(item.title || item.name || "Bản tin")}</span>
					<span class="vnt-home__feed-meta">${escapeHtml(item.time_ago || timeAgo(item.date))}</span>
				</span>
				<i class="fa fa-angle-right" aria-hidden="true"></i>`;
			button.addEventListener("click", () => frappe.set_route("Form", "VNT New Feed", item.name));
			list.appendChild(button);
		});
	}

	async function loadFeeds() {
		await Promise.all([
			frappe
				.xcall("vinatex.api.custom_todo.get_my_todos", { limit: 30 })
				.then((items) => renderTodos(Array.isArray(items) ? items : []))
				.catch((error) => {
					console.error("Không thể tải công việc", error);
					setFeedEmpty("todo", "Không tải được danh sách công việc.");
				}),
			frappe
				.xcall("vinatex.api.custom_todo.get_vnt_news", { limit: 10 })
				.then((items) => renderNews(Array.isArray(items) ? items : []))
				.catch((error) => {
					console.error("Không thể tải bản tin", error);
					setFeedEmpty("news", "Không tải được bản tin.");
				}),
		]);
	}

	function applyShortcutLinks(employee) {
		const range = monthWindow();
		const replacements = {
			employee: employee || "",
			month: range.month,
			year: range.year,
			from_date: range.from_date,
			to_date: range.to_date,
		};
		home.querySelectorAll("[data-route-template]").forEach((link) => {
			let route = link.dataset.routeTemplate || "";
			Object.entries(replacements).forEach(([key, value]) => {
				route = route.replaceAll(`{{${key}}}`, encodeURIComponent(value));
			});
			if (!employee && route.includes("employee=")) {
				link.setAttribute("aria-disabled", "true");
				link.addEventListener("click", (event) => {
					event.preventDefault();
					showAlert("Tài khoản chưa được liên kết với hồ sơ nhân sự.");
				});
				return;
			}
			link.href = route;
		});
	}

	async function loadEmployeeLinks() {
		try {
			const employee = await frappe.xcall(
				"vinatex.vinatex.doctype.overrides.employee.get_employee_for_current_user"
			);
			applyShortcutLinks(employee || "");
		} catch (error) {
			console.error("Không thể xác định hồ sơ nhân sự", error);
			applyShortcutLinks("");
		}
	}

	function addMonths(year, month, delta) {
		const date = new Date(year, month - 1 + delta, 1);
		return { year: date.getFullYear(), month: date.getMonth() + 1 };
	}

	function dateKey(year, month, day) {
		return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
	}

	function peopleNames(people) {
		return (people || [])
			.map((person) => person.employee_name || person.employee || "")
			.filter(Boolean)
			.join(", ");
	}

	function eventLines(bucket) {
		if (!bucket) return [];
		const lines = [];
		const pushTrips = (items, prefix) => {
			(items || []).forEach((item) => {
				const people = peopleNames(item.people);
				lines.push(`${prefix}: ${item.destination || "Chưa có địa điểm"}${people ? ` · ${people}` : ""}`);
			});
		};
		pushTrips(bucket.leader_trips, "Lãnh đạo công tác");
		pushTrips(bucket.trips, "Công tác");
		(bucket.meetings || []).forEach((item) => {
			const time = [item.start_time, item.end_time].filter(Boolean).join(" – ");
			lines.push(`Họp${time ? ` ${time}` : ""}: ${item.note || item.room_name || "Chưa có nội dung"}`);
		});
		(bucket.leader_leaves || bucket.leader_leader_leaves || []).forEach((item) => {
			const people = peopleNames(item.people);
			lines.push(`Lãnh đạo nghỉ: ${item.leave_type || "Nghỉ phép"}${people ? ` · ${people}` : ""}`);
		});
		return lines;
	}

	function renderCalendar() {
		const grid = home.querySelector("[data-calendar-grid]");
		const title = home.querySelector("[data-calendar-title]");
		const { year, month, tab } = calendarState;
		const byDate = calendarState.data[tab] || {};
		const firstDay = new Date(year, month - 1, 1);
		const daysInMonth = new Date(year, month, 0).getDate();
		const offset = (firstDay.getDay() + 6) % 7;
		const today = (frappe.datetime && frappe.datetime.get_today()) || dateKey(new Date().getFullYear(), new Date().getMonth() + 1, new Date().getDate());
		const weekdays = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

		title.textContent = `Tháng ${month} ${year}`;
		grid.textContent = "";
		weekdays.forEach((weekday, index) => {
			const element = document.createElement("div");
			element.className = `vnt-home__weekday${index > 4 ? " is-weekend" : ""}`;
			element.textContent = weekday;
			grid.appendChild(element);
		});
		for (let index = 0; index < offset; index += 1) {
			const empty = document.createElement("div");
			empty.className = "vnt-home__day is-empty";
			grid.appendChild(empty);
		}

		for (let day = 1; day <= daysInMonth; day += 1) {
			const key = dateKey(year, month, day);
			const lines = eventLines(byDate[key]);
			const weekday = new Date(year, month - 1, day).getDay();
			const element = document.createElement("div");
			element.className = "vnt-home__day";
			if (weekday === 0 || weekday === 6) element.classList.add("is-weekend");
			if (key === today) element.classList.add("is-today");
			if (lines.length) {
				element.classList.add("has-event");
				element.tabIndex = 0;
				element.setAttribute("aria-label", `Ngày ${day}, ${lines.length} sự kiện`);
			}
			element.append(document.createTextNode(String(day)));
			if (lines.length) {
				const dot = document.createElement("span");
				dot.className = "vnt-home__event-dot";
				const popover = document.createElement("span");
				popover.className = "vnt-home__event-popover";
				popover.innerHTML = `<strong>Ngày ${day}/${month}/${year}</strong>${lines
					.map((line) => `<span>${escapeHtml(line)}</span>`)
					.join("")}`;
				element.append(dot, popover);
				element.addEventListener("click", () => {
					home.querySelectorAll(".vnt-home__day.is-open").forEach((dayElement) => {
						if (dayElement !== element) dayElement.classList.remove("is-open");
					});
					element.classList.toggle("is-open");
				});
			}
			grid.appendChild(element);
		}
	}

	async function loadCalendar() {
		const requestId = ++calendarState.requestId;
		const grid = home.querySelector("[data-calendar-grid]");
		grid.innerHTML = '<div class="vnt-home__empty" style="grid-column:1/-1;margin:0">Đang tải lịch…</div>';
		try {
			const result = await frappe.xcall("vinatex.api.custom_calendar.get_department_calendar", {
				year: calendarState.year,
				month: calendarState.month,
			});
			if (requestId !== calendarState.requestId) return;
			calendarState.data.common = (result && (result.common_by_date || result.by_date)) || {};
			calendarState.data.personal = (result && result.personal_by_date) || {};
		} catch (error) {
			console.error("Không thể tải lịch", error);
			if (requestId !== calendarState.requestId) return;
			calendarState.data = { common: {}, personal: {} };
			showAlert("Không tải được lịch.", "red");
		}
		renderCalendar();
	}

	home.addEventListener("click", (event) => {
		const action = event.target.closest("[data-action]");
		if (action) {
			if (action.dataset.action === "todos-all") {
				frappe.set_route("List", "ToDo", {
					allocated_to: frappe.session.user,
					status: "Open",
				});
			}
			if (action.dataset.action === "news-all") frappe.set_route("List", "VNT New Feed");
			return;
		}

		const kpi = event.target.closest("[data-kpi-key]");
		if (kpi) {
			const config = KPI_CONFIG.find((item) => item.key === kpi.dataset.kpiKey);
			if (config && config.report) {
				go(
					reportUrl(
						config.report,
						Object.assign({}, config.monthFilters ? monthWindow() : {}, config.extra || {})
					)
				);
			}
			if (config && config.key === "remaining_leave") go("/app/leave-application");
			return;
		}

		const tab = event.target.closest("[data-calendar-tab]");
		if (tab) {
			calendarState.tab = tab.dataset.calendarTab;
			home.querySelectorAll("[data-calendar-tab]").forEach((button) => {
				const active = button.dataset.calendarTab === calendarState.tab;
				button.classList.toggle("is-active", active);
				button.setAttribute("aria-selected", String(active));
			});
			renderCalendar();
			return;
		}

		const calendarAction = event.target.closest("[data-calendar-action]");
		if (!calendarAction) return;
		if (calendarAction.dataset.calendarAction === "today") {
			const now = new Date();
			calendarState.year = now.getFullYear();
			calendarState.month = now.getMonth() + 1;
		} else {
			const delta = calendarAction.dataset.calendarAction === "prev" ? -1 : 1;
			const next = addMonths(calendarState.year, calendarState.month, delta);
			calendarState.year = next.year;
			calendarState.month = next.month;
		}
		loadCalendar();
	});

	Promise.allSettled([loadKpis(), loadFeeds(), loadEmployeeLinks(), loadCalendar()]);
})();

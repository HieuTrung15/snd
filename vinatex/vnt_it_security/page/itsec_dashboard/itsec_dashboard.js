frappe.pages["itsec-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("IT Security Dashboard"),
		single_column: true,
	});

	let dashboard = null;

	page.set_primary_action(__("Sync Now"), () => {
		frappe.confirm(__("Queue nightly sync for all sources?"), () => {
			frappe.call({
				method: "vinatex.vnt_itsec.sync.run.trigger_sync",
				freeze: true,
				callback: (resp) => {
					if (!resp || resp.exc) {
						return;
					}
					frappe.show_alert({ message: __("Sync job queued"), indicator: "green" });
				},
			});
		});
	});

	page.add_field({
		fieldname: "days",
		label: __("Days"),
		fieldtype: "Select",
		options: ["7", "30", "90"],
		default: "30",
		change: () => {
			if (dashboard) {
				dashboard.refresh();
			}
		},
	});

	page.set_secondary_action(__("Refresh"), () => {
		if (dashboard) {
			dashboard.refresh();
		}
	}, "refresh");

	loadItsecAssets(() => {
		dashboard = new ItsecDashboard(page);
	});
};

function loadItsecAssets(done) {
	frappe.require("/assets/vinatex/css/itsec_dashboard.css", () => {});
	if (window.Highcharts) {
		setItsecHighchartsTheme();
		done();
		return;
	}
	frappe.require("/assets/vinatex/js/vendor/highcharts/highcharts.js", () => {
		setItsecHighchartsTheme();
		done();
	});
}

function setItsecHighchartsTheme() {
	if (window.itsecHighchartsTheme) {
		return;
	}
	window.itsecHighchartsTheme = true;
	Highcharts.setOptions({
		chart: {
			backgroundColor: "transparent",
			style: { fontFamily: "Sora, Urbanist, Plus Jakarta Sans, Segoe UI, sans-serif" },
		},
		title: { style: { color: "#101828", fontWeight: "600" } },
		subtitle: { style: { color: "#667085" } },
		colors: ["#F04438", "#F79009", "#2F80ED", "#12B76A", "#8F95B2", "#344054"],
		xAxis: {
			gridLineColor: "rgba(15, 23, 42, 0.08)",
			lineColor: "rgba(15, 23, 42, 0.2)",
			labels: { style: { color: "#667085" } },
		},
		yAxis: {
			gridLineColor: "rgba(15, 23, 42, 0.08)",
			labels: { style: { color: "#667085" } },
			title: { style: { color: "#667085" } },
		},
		legend: {
			itemStyle: { color: "#344054", fontWeight: "600" },
			itemHoverStyle: { color: "#101828" },
		},
		tooltip: {
			backgroundColor: "#101828",
			style: { color: "#ffffff" },
			borderRadius: 10,
			borderWidth: 0,
		},
		credits: { enabled: false },
	});
}

class ItsecDashboard {
	constructor(page) {
		this.page = page;
		this.$wrapper = $(page.main);
		this.charts = {};
		this.setup();
		this.refresh();
	}

	setup() {
		this.$wrapper.html(`
			<div class="itsec-dashboard">
				<div class="itsec-hero">
					<div>
						<div class="itsec-hero-kicker">Security posture</div>
						<div class="itsec-hero-title">IT Security Dashboard</div>
						<div class="itsec-hero-sub">Live view of exposure, advisories, and remediation health.</div>
					</div>
					<div class="itsec-hero-tags">
						<span class="itsec-pill" data-key="window_label">Last 30 days</span>
						<span class="itsec-pill itsec-pill--low" data-key="last_sync">Last sync: -</span>
					</div>
				</div>
				<div class="itsec-kpis">
					<div class="itsec-card" data-tone="info" data-link="cve_total"><div class="itsec-card-label">Total CVEs</div><div class="itsec-card-value" data-key="cve_total">0</div><div class="itsec-card-meta">All time</div></div>
					<div class="itsec-card" data-tone="warning" data-link="cve_new"><div class="itsec-card-label">New CVEs</div><div class="itsec-card-value" data-key="cve_new">0</div><div class="itsec-card-meta">Window</div></div>
					<div class="itsec-card" data-tone="danger" data-link="critical_high"><div class="itsec-card-label">Critical + High</div><div class="itsec-card-value" data-key="critical_high">0</div><div class="itsec-card-meta">Immediate focus</div></div>
					<div class="itsec-card" data-tone="info" data-link="assets_total"><div class="itsec-card-label">IT Assets</div><div class="itsec-card-value" data-key="assets_total">0</div><div class="itsec-card-meta">Tracked</div></div>
					<div class="itsec-card" data-tone="warning" data-link="advisories_open"><div class="itsec-card-label">Open Advisories</div><div class="itsec-card-value" data-key="advisories_open">0</div><div class="itsec-card-meta">Active</div></div>
					<div class="itsec-card" data-tone="danger" data-link="affected_open"><div class="itsec-card-label">Affected Assets</div><div class="itsec-card-value" data-key="affected_open">0</div><div class="itsec-card-meta">Open/In progress</div></div>
					<div class="itsec-card" data-tone="warning" data-link="tickets_open"><div class="itsec-card-label">Open Tickets</div><div class="itsec-card-value" data-key="tickets_open">0</div><div class="itsec-card-meta">Remediation</div></div>
					<div class="itsec-card" data-tone="danger" data-link="tickets_overdue"><div class="itsec-card-label">Tickets Overdue</div><div class="itsec-card-value" data-key="tickets_overdue">0</div><div class="itsec-card-meta">SLA risk</div></div>
				</div>
				<div class="itsec-grid itsec-grid-2">
					<div class="itsec-panel">
						<div class="itsec-panel-title">Severity Breakdown</div>
						<div id="itsec-severity-chart" class="itsec-chart"></div>
					</div>
					<div class="itsec-panel">
						<div class="itsec-panel-title">CVE Trend</div>
						<div id="itsec-trend-chart" class="itsec-chart"></div>
					</div>
				</div>
				<div class="itsec-grid itsec-grid-3">
					<div class="itsec-panel">
						<div class="itsec-panel-title">Asset Exposure Mix</div>
						<div id="itsec-exposure-chart" class="itsec-chart-sm"></div>
					</div>
					<div class="itsec-panel">
						<div class="itsec-panel-title">Affected Asset Status</div>
						<div id="itsec-affected-chart" class="itsec-chart-sm"></div>
					</div>
					<div class="itsec-panel">
						<div class="itsec-panel-title">Ticket Status</div>
						<div id="itsec-ticket-chart" class="itsec-chart-sm"></div>
					</div>
				</div>
				<div class="itsec-grid itsec-grid-2">
					<div class="itsec-panel">
						<div class="itsec-panel-title">Source Status</div>
						<div id="itsec-sources-table" class="itsec-table-wrap"></div>
					</div>
					<div class="itsec-panel">
						<div class="itsec-panel-title">Recent CVEs</div>
						<div id="itsec-recent-table" class="itsec-table-wrap"></div>
					</div>
				</div>
			</div>
		`);
		this.bindKpiLinks();
	}

	bindKpiLinks() {
		this.$wrapper.on("click", ".itsec-card[data-link]", (event) => {
			const key = $(event.currentTarget).data("link");
			const days = parseInt(this.page.fields_dict.days.get_value() || 30, 10);
			const today = frappe.datetime.now_date();
			const since = frappe.datetime.add_days(today, -(days - 1));

			const linkMap = {
				cve_total: () => ({ doctype: "VNT CVE" }),
				cve_new: () => ({
					doctype: "VNT CVE",
					filters: { published_date: [">=", since] },
				}),
				critical_high: () => ({
					doctype: "VNT CVE",
					filters: { severity: ["in", ["Critical", "High"]] },
				}),
				assets_total: () => ({ doctype: "VNT IT Asset" }),
				advisories_open: () => ({
					doctype: "VNT Vulnerability Advisory",
					filters: { status: ["not in", ["Closed"]] },
				}),
				affected_open: () => ({
					doctype: "VNT Affected Asset",
					filters: { status: ["in", ["Open", "In Progress"]] },
				}),
				tickets_open: () => ({
					doctype: "VNT Remediation Ticket",
					filters: { status: ["not in", ["Done", "Rejected"]] },
				}),
				tickets_overdue: () => ({
					doctype: "VNT Remediation Ticket",
					filters: {
						status: ["not in", ["Done", "Rejected"]],
						sla_due_date: ["<", today],
					},
				}),
			};

			const target = linkMap[key] ? linkMap[key]() : null;
			if (!target) {
				return;
			}
			frappe.route_options = target.filters || null;
			frappe.set_route("List", target.doctype);
		});
	}

	refresh() {
		const days = parseInt(this.page.fields_dict.days.get_value() || 30, 10);
		this.$wrapper.find('[data-key="window_label"]').text(`Last ${days} days`);
		frappe.call({
			method: "vinatex.vnt_itsec.api.dashboard.get_dashboard_data",
			args: { days, limit: 10 },
			callback: (resp) => {
				if (!resp || resp.exc) {
					return;
				}
				const data = resp.message || {};
				this.renderOverview(data.overview || {});
				this.renderSeverity(data.severity || []);
				this.renderTrend(data.cve_trend || []);
				this.renderExposure(data.exposure_breakdown || []);
				this.renderAffected(data.affected_breakdown || []);
				this.renderTickets(data.ticket_breakdown || []);
				this.renderSources(data.sources || []);
				this.renderRecent(data.recent || []);
			},
		});
	}

	renderOverview(overview) {
		Object.keys(overview).forEach((key) => {
			this.$wrapper.find(`[data-key="${key}"]`).text(overview[key] || 0);
		});
	}

	renderSeverity(severity) {
		const data = severity.map((row) => ({ name: row.label, y: row.value || 0 }));
		this.renderChart("severity", "itsec-severity-chart", {
			chart: { type: "pie" },
			title: { text: null },
			plotOptions: {
				pie: {
					innerSize: "60%",
					dataLabels: { enabled: true, format: "{point.name}: {point.y}" },
				},
			},
			series: [{ name: "CVEs", data }],
		});
	}

	renderTrend(trend) {
		const categories = trend.map((row) => row.date);
		const totals = trend.map((row) => row.total || 0);
		const critical = trend.map((row) => row.critical_high || 0);
		this.renderChart("trend", "itsec-trend-chart", {
			chart: { type: "areaspline" },
			title: { text: null },
			xAxis: { categories },
			yAxis: { title: { text: null } },
			plotOptions: { areaspline: { fillOpacity: 0.12 } },
			series: [
				{ name: "Total CVEs", data: totals },
				{ name: "Critical + High", data: critical },
			],
		});
	}

	renderExposure(exposure) {
		const categories = exposure.map((row) => row.label);
		const values = exposure.map((row) => row.value || 0);
		this.renderChart("exposure", "itsec-exposure-chart", {
			chart: { type: "column" },
			title: { text: null },
			xAxis: { categories },
			yAxis: { title: { text: null } },
			series: [{ name: "Assets", data: values }],
		});
	}

	renderAffected(affected) {
		const data = affected.map((row) => ({ name: row.label, y: row.value || 0 }));
		this.renderChart("affected", "itsec-affected-chart", {
			chart: { type: "bar" },
			title: { text: null },
			xAxis: { categories: affected.map((row) => row.label) },
			yAxis: { title: { text: null } },
			series: [{ name: "Affected Assets", data: data.map((row) => row.y) }],
		});
	}

	renderTickets(tickets) {
		const data = tickets.map((row) => ({ name: row.label, y: row.value || 0 }));
		this.renderChart("tickets", "itsec-ticket-chart", {
			chart: { type: "pie" },
			title: { text: null },
			plotOptions: {
				pie: { innerSize: "52%", dataLabels: { enabled: false } },
			},
			series: [{ name: "Tickets", data }],
		});
	}

	renderSources(sources) {
		if (!sources.length) {
			$("#itsec-sources-table").html('<div class="itsec-muted">No sources configured</div>');
			this.$wrapper.find('[data-key="last_sync"]').text("Last sync: -");
			return;
		}

		const syncTimes = sources
			.map((row) => row.last_successful_sync_at)
			.filter((row) => row);
		const lastSync = syncTimes.length
			? frappe.datetime.str_to_user(syncTimes.sort().slice(-1)[0])
			: "-";
		this.$wrapper.find('[data-key="last_sync"]').text(`Last sync: ${lastSync}`);

		let rows = sources
			.map((row) => {
				const lastSyncRow = row.last_successful_sync_at
					? frappe.datetime.str_to_user(row.last_successful_sync_at)
					: "-";
				const watermark = row.watermark_source_ts
					? frappe.datetime.str_to_user(row.watermark_source_ts)
					: "-";
				const enabledLabel = row.enabled
					? '<span class="itsec-pill itsec-pill--low">Yes</span>'
					: '<span class="itsec-pill itsec-pill--unknown">No</span>';
				return `
					<tr>
						<td>${frappe.utils.escape_html(row.source_code || "")}</td>
						<td>${enabledLabel}</td>
						<td>${frappe.utils.escape_html(row.sync_mode || "")}</td>
						<td>${lastSyncRow}</td>
						<td>${watermark}</td>
					</tr>
				`;
			})
			.join("");

		const table = `
			<table class="itsec-table">
				<thead>
					<tr>
						<th>Source</th>
						<th>Enabled</th>
						<th>Mode</th>
						<th>Last Sync</th>
						<th>Watermark</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`;
		$("#itsec-sources-table").html(table);
	}

	renderRecent(recent) {
		if (!recent.length) {
			$("#itsec-recent-table").html('<div class="itsec-muted">No CVEs yet</div>');
			return;
		}
		let rows = recent
			.map((row) => {
				const published = row.published_date
					? frappe.datetime.str_to_user(row.published_date)
					: "-";
				const desc = row.description
					? frappe.utils.escape_html(this.truncateText(row.description, 120))
					: "";
				const pill = this.getSeverityPill(row.severity || "Unknown");
				return `
					<tr>
						<td>${frappe.utils.escape_html(row.cve_id || "")}</td>
						<td>${pill}</td>
						<td>${published}</td>
						<td>${desc}</td>
					</tr>
				`;
			})
			.join("");

		const table = `
			<table class="itsec-table">
				<thead>
					<tr>
						<th>CVE</th>
						<th>Severity</th>
						<th>Published</th>
						<th>Description</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`;
		$("#itsec-recent-table").html(table);
	}

	truncateText(text, maxLength) {
		const value = String(text || "");
		if (value.length <= maxLength) {
			return value;
		}
		const trimmed = value.slice(0, Math.max(0, maxLength - 3)).trim();
		return `${trimmed}...`;
	}

	getSeverityPill(severity) {
		const key = String(severity || "Unknown").toLowerCase();
		if (key === "critical") {
			return '<span class="itsec-pill itsec-pill--critical">Critical</span>';
		}
		if (key === "high") {
			return '<span class="itsec-pill itsec-pill--high">High</span>';
		}
		if (key === "medium") {
			return '<span class="itsec-pill itsec-pill--medium">Medium</span>';
		}
		if (key === "low") {
			return '<span class="itsec-pill itsec-pill--low">Low</span>';
		}
		return '<span class="itsec-pill itsec-pill--unknown">Unknown</span>';
	}

	renderChart(key, containerId, options) {
		const container = document.getElementById(containerId);
		if (!container) {
			return;
		}
		if (!this.charts[key]) {
			this.charts[key] = Highcharts.chart(containerId, options);
			return;
		}
		this.charts[key].update(options, true, true);
	}
}

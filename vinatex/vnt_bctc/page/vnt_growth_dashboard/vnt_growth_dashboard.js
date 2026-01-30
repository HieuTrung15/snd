frappe.pages["vnt-growth-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Hành trình tăng trưởng"),
		single_column: true,
	});

	let dashboard = null;

	loadGrowthAssets(() => {
		dashboard = new GrowthDashboard(page);
		dashboard.initFilters();
	});
};

function loadGrowthAssets(done) {
	frappe.require("/assets/vinatex/css/vnt_bctc_growth_dashboard.css", () => {});
	const scripts = [
		"/assets/vinatex/js/vendor/highcharts/highcharts.js",
		"/assets/vinatex/js/vendor/highcharts/highcharts-more.js",
		"/assets/vinatex/js/vendor/highcharts/modules/treemap.js",
		"/assets/vinatex/js/vendor/highcharts/modules/waterfall.js",
		"/assets/vinatex/js/vendor/highcharts/modules/solid-gauge.js",
	];
	let chain = Promise.resolve();
	scripts.forEach((src) => {
		chain = chain.then(
			() =>
				new Promise((resolve) => {
					frappe.require(src, () => resolve());
				})
		);
	});
	chain.then(() => {
		setGrowthTheme();
		done();
	});
}

function setGrowthTheme() {
	if (window.vntGrowthThemeApplied || !window.Highcharts) {
		return;
	}
	window.vntGrowthThemeApplied = true;
	Highcharts.setOptions({
		chart: {
			backgroundColor: "transparent",
			style: { fontFamily: "Sora, Manrope, Plus Jakarta Sans, Segoe UI, sans-serif" },
		},
		title: { style: { color: "#1B2559", fontWeight: "700" } },
		subtitle: { style: { color: "#6B7280" } },
		colors: ["#2563EB", "#14B8A6", "#F97316", "#EF4444", "#6366F1", "#0EA5E9"],
		xAxis: {
			gridLineColor: "rgba(15, 23, 42, 0.08)",
			lineColor: "rgba(15, 23, 42, 0.2)",
			labels: { style: { color: "#64748B" } },
		},
		yAxis: {
			gridLineColor: "rgba(15, 23, 42, 0.08)",
			labels: { style: { color: "#64748B" } },
			title: { style: { color: "#64748B" } },
		},
		legend: {
			itemStyle: { color: "#0F172A", fontWeight: "600" },
			itemHoverStyle: { color: "#1D4ED8" },
		},
		tooltip: {
			backgroundColor: "#0F172A",
			style: { color: "#FFFFFF" },
			borderRadius: 10,
			borderWidth: 0,
		},
		credits: { enabled: false },
	});
}

class GrowthDashboard {
	constructor(page) {
		this.page = page;
		this.$wrapper = $(page.main);
		this.charts = {};
		this.renderLayout();
		this.refresh();
	}

	renderLayout() {
		this.$wrapper.html(`
			<div class="growth-dashboard">
				<section class="growth-hero">
					<div>
						<div class="growth-kicker">HÀNH TRÌNH TĂNG TRƯỞNG</div>
						<h1>Phân tích bốn trụ cột kinh doanh</h1>
						<p>Tổng quan hiệu suất, xác định động lực tăng trưởng và rủi ro trọng yếu.</p>
					</div>
					
				</section>
				<section class="growth-filters">
					<div class="growth-filter-title">Bộ lọc</div>
					<div class="growth-filter-grid">
						<div class="growth-filter" data-field="actual_doc"></div>
						<div class="growth-filter" data-field="plan_doc"></div>
						<div class="growth-filter" data-field="company"></div>
						<div class="growth-filter" data-field="month"></div>
						<div class="growth-filter" data-field="year_scope"></div>
						<div class="growth-filter" data-field="data_type"></div>
					</div>
				</section>

				<section class="growth-kpis">
					<div class="growth-card">
						<p>Tổng Doanh thu</p>
						<h3 data-key="revenue_month">0</h3>
						<span data-key="revenue_month_delta"></span>
					</div>
					<div class="growth-card">
						<p>Tổng Doanh thu lũy kế</p>
						<h3 data-key="revenue_ytd">0</h3>
						<span data-key="revenue_ytd_delta"></span>
					</div>
					<div class="growth-card">
						<p>Tổng LNTT</p>
						<h3 data-key="profit_month">0</h3>
						<span data-key="profit_month_delta"></span>
					</div>
					<div class="growth-card">
						<p>Tổng LNTT lũy kế</p>
						<h3 data-key="profit_ytd">0</h3>
						<span data-key="profit_ytd_delta"></span>
					</div>
				</section>

				<section class="growth-grid growth-grid-2">
					<div class="growth-panel">
						<div class="growth-panel-title">Xu hướng Doanh thu & LNTT qua các tháng</div>
						<div id="growth-trend-chart" class="growth-chart-lg"></div>
					</div>
					<div class="growth-panel">
						<div class="growth-panel-title">Cơ cấu Lợi nhuận từ 4 Nhóm</div>
						<div id="growth-waterfall-chart" class="growth-chart-lg"></div>
					</div>
				</section>

				<section class="growth-alerts">
					<h3>Cảnh báo & Điểm nhấn</h3>
					<div class="growth-alert-list" data-key="alerts"></div>
				</section>

				<section class="growth-section">
					<header>
						<h2>Nhóm I - Động lực mới Ngoài ngành</h2>
						<p>Drill-down 6 mục con và điểm nóng tài chính.</p>
					</header>
					<div class="growth-grid growth-grid-3">
						<div class="growth-panel">
							<div class="growth-panel-title">Cơ cấu Doanh thu/LNTT Nhóm I</div>
							<div id="growth-group1-treemap" class="growth-chart-md"></div>
						</div>
						<div class="growth-panel">
							<div class="growth-panel-title">Hiệu suất lũy kế so với Kế hoạch</div>
							<div id="growth-group1-bar" class="growth-chart-md"></div>
						</div>
						<div class="growth-panel">
							<div class="growth-panel-title">Kinh doanh tài chính (Mục 5)</div>
							<div id="growth-group1-donut" class="growth-chart-md"></div>
						</div>
					</div>
				</section>

				<section class="growth-section">
					<header>
						<h2>Nhóm II & III - Động lực Cốt lõi</h2>
						<p>Động lực mới trong ngành và các nguồn lực cũ.</p>
					</header>
					<div class="growth-grid growth-grid-2">
						<div class="growth-panel">
							<div class="growth-panel-title">KPI Nhóm II</div>
							<div class="growth-kpi-list" data-key="group2_kpis"></div>
						</div>
						<div class="growth-panel">
							<div class="growth-panel-title">So sánh Hiệu suất Động lực cũ</div>
							<div id="growth-group3-bar" class="growth-chart-md"></div>
						</div>
					</div>
					<div class="growth-panel">
						<div class="growth-panel-title">Phân tích Lợi nhuận từ Đầu tư</div>
						<div id="growth-investment-waterfall" class="growth-chart-md"></div>
					</div>
				</section>

				<section class="growth-section">
					<header>
						<h2>Nhóm IV - Tối ưu Chi phí Vận hành</h2>
						<p>Giám sát chi phí và mức độ kiểm soát ngân sách.</p>
					</header>
					<div class="growth-grid growth-grid-3">
						<div class="growth-panel">
							<div class="growth-panel-title">Xu hướng Chi phí Vận hành</div>
							<div id="growth-cost-line" class="growth-chart-md"></div>
						</div>
						<div class="growth-panel">
							<div class="growth-panel-title">Kiểm soát Chi phí</div>
							<div id="growth-cost-gauge" class="growth-chart-sm"></div>
						</div>
						<div class="growth-panel">
							<div class="growth-panel-title">Dự kiến Chi phí <span data-key="cost_forecast_year">-</span></div>
							<div class="growth-forecast" data-key="cost_forecast"></div>
						</div>
					</div>
				</section>
			</div>
		`);
	}

	initFilters() {
		const defaultActualDoc = "FR-ACT-2026-0002";
		this.controls = {};
		const fields = [
			{
				fieldname: "actual_doc",
				label: "Bảng thực tế",
				fieldtype: "Link",
				options: "VNT Financial Actual Summary",
				default: defaultActualDoc,
				change: () => this.syncFromActualDoc(),
			},
			{
				fieldname: "plan_doc",
				label: "Bảng kế hoạch",
				fieldtype: "Link",
				options: "VNT Financial Plan Summary",
				change: () => this.refresh(),
			},
			{
				fieldname: "company",
				label: "Công ty",
				fieldtype: "Link",
				options: "Company",
				change: () => this.refresh(),
			},
			{
				fieldname: "month",
				label: "Tháng",
				fieldtype: "Select",
				options: ["Cả năm", ...Array.from({ length: 12 }, (_, i) => `${i + 1}`)],
				default: `Cả năm`,
				change: () => this.refresh(),
			},
			{
				fieldname: "year_scope",
				label: "Năm hiển thị",
				fieldtype: "Select",
				options: [
					`${new Date().getFullYear()}`,
					`${new Date().getFullYear() - 1}`,
				],
				change: () => this.refresh(),
			},
			{
				fieldname: "data_type",
				label: "Loại dữ liệu",
				fieldtype: "Select",
				options: ["Actual", "Plan"],
				default: "Actual",
				change: () => this.refresh(),
			},
		];

		fields.forEach((field) => {
			const wrapper = this.$wrapper.find(`.growth-filter[data-field="${field.fieldname}"]`)[0];
			if (!wrapper) {
				return;
			}
			const control = frappe.ui.form.make_control({
				df: field,
				parent: wrapper,
				render_input: true,
			});
			control.make();
			this.controls[field.fieldname] = control;
			if (field.default) {
				control.set_value(field.default);
			}
		});

		if (this.controls.actual_doc && !this.controls.actual_doc.get_value()) {
			this.controls.actual_doc.set_value(defaultActualDoc);
		}
		this.syncFromActualDoc();
	}

	syncFromActualDoc() {
		const control = this.controls && this.controls.actual_doc;
		const docname = control ? control.get_value() : null;
		if (!docname) {
			this.currentFiscalYear = null;
			this.refresh();
			return;
		}
		frappe.db
			.get_value("VNT Financial Actual Summary", docname, ["company", "fiscal_year"])
			.then((r) => {
				let updatePromise = Promise.resolve();
					if (r && r.message) {
						if (this.controls.company && r.message.company) {
							this.controls.company.set_value(r.message.company);
						}
						if (r.message.fiscal_year) {
							this.currentFiscalYear = r.message.fiscal_year;
							updatePromise = this.updateYearScopeOptions(r.message.fiscal_year);
						}
					}
				return updatePromise;
			})
			.then(() => this.refresh());
	}

	updateYearScopeOptions(fiscalYearName) {
		const control = this.controls && this.controls.year_scope;
		if (!control || !fiscalYearName) {
			return Promise.resolve();
		}
		return frappe.db.get_value("Fiscal Year", fiscalYearName, "year_start_date").then((r) => {
			const startDate = r && r.message ? r.message.year_start_date : null;
			if (!startDate) {
				return;
			}
			const baseYear = new Date(startDate).getFullYear();
			if (!baseYear || Number.isNaN(baseYear)) {
				return;
			}
			const options = [`${baseYear}`, `${baseYear - 1}`];
			control.df.options = options;
			control.refresh();
			if (!options.includes(control.get_value())) {
				control.set_value(`${baseYear}`);
			}
		});
	}

	refresh() {
		if (!this.controls) {
			return;
		}
		const filters = {
			company: this.controls.company.get_value(),
			fiscal_year: this.currentFiscalYear || null,
			month: this.controls.month.get_value() === "Cả năm" ? "all" : this.controls.month.get_value(),
			data_type: this.controls.data_type.get_value(),
			year_scope: this.controls.year_scope.get_value(),
			actual_doc: this.controls.actual_doc.get_value(),
			plan_doc: this.controls.plan_doc.get_value(),
		};

		frappe.call({
			method: "vinatex.vnt_bctc.page.vnt_growth_dashboard.vnt_growth_dashboard.get_growth_dashboard_data",
			args: filters,
			freeze: true,
			callback: (r) => {
				if (!r || !r.message) {
					return;
				}
				this.renderData(r.message, filters);
			},
		});
	}

	renderData(payload, filters) {
		const meta = payload.meta || {};
		const yearScope = payload.year_scope || filters.year_scope;
		const actual = payload.actual || payload.plan;
		const plan = payload.plan;
		if (!actual) {
			return;
		}

		this.$wrapper.find('[data-key="data_type"]').text(filters.data_type || "Actual");
		this.$wrapper.find('[data-key="month_label"]').text(meta.month_label || "-");
		const displayYear = meta.display_year || meta.fiscal_year || "-";
		this.$wrapper.find('[data-key="fiscal_year"]').text(displayYear);
		this.$wrapper.find('[data-key="cost_forecast_year"]').text(displayYear);
		if (yearScope === "prev") {
			this.$wrapper.find('[data-key="month_label"]').text(`${meta.month_label || "-"} (Năm trước)`);
		}

		const isFullYear = filters.month === "all";
		this.renderKpis(actual.totals, plan ? plan.totals : null, isFullYear);
		this.renderAlerts(actual, plan);
		this.renderTrend(actual.trends);
		this.renderWaterfall(actual.groups);
		this.renderGroup1(actual.group1_items, plan ? plan.group1_items : null);
		this.renderGroup2(actual.group2_items, plan ? plan.group2_items : null);
		this.renderGroup3(actual.group3_items);
		this.renderInvestment(actual.investment_breakdown);
		this.renderCost(actual.cost_trend, actual.groups, plan ? plan.groups : null);
	}

	renderKpis(totals, planTotals, isFullYear) {
		const $root = this.$wrapper;
		const revenueMonth = totals?.revenue_month || 0;
		const revenueYtd = totals?.revenue_ytd || 0;
		const profitMonth = totals?.profit_month || 0;
		const profitYtd = totals?.profit_ytd || 0;

		$root.find('[data-key="revenue_month"]').text(formatNumber(revenueMonth));
		$root.find('[data-key="revenue_ytd"]').text(formatNumber(revenueYtd));
		$root.find('[data-key="profit_month"]').text(formatNumber(profitMonth));
		$root.find('[data-key="profit_ytd"]').text(formatNumber(profitYtd));

		const monthCompareLabel = isFullYear ? "So với cùng kỳ" : "So với tháng trước";
		const revenueMonthCompare = isFullYear ? totals?.revenue_prev_ytd : totals?.revenue_prev_month;
		const profitMonthCompare = isFullYear ? totals?.profit_prev_ytd : totals?.profit_prev_month;

		$root.find('[data-key="revenue_month_delta"]').text(
			renderDelta(revenueMonth, revenueMonthCompare, monthCompareLabel)
		);
		$root.find('[data-key="revenue_ytd_delta"]').text(
			renderDelta(revenueYtd, totals?.revenue_prev_ytd, "So với cùng kỳ")
		);
		$root.find('[data-key="profit_month_delta"]').text(
			renderDelta(profitMonth, profitMonthCompare, monthCompareLabel)
		);
		$root.find('[data-key="profit_ytd_delta"]').text(
			renderDelta(profitYtd, totals?.profit_prev_ytd, "So với cùng kỳ")
		);

		if (planTotals) {
			const planDelta = renderDelta(profitYtd, planTotals.profit_ytd, "So với kế hoạch");
			$root.find('[data-key="profit_ytd_delta"]').text(planDelta);
		}
	}

	renderAlerts(actual, plan) {
		const alerts = [];
		const groups = actual.groups || [];
		groups.forEach((group) => {
			const name = group.name || "";
			const revenueDelta = calcPercent(group.revenue_month, group.revenue_prev_month);
			const revenueYoY = calcPercent(group.revenue_ytd, group.revenue_prev_ytd);
			const costDelta = calcPercent(group.cost_month, group.cost_prev_month);

			if (name.includes("Nhóm 4")) {
				if (costDelta <= -10) {
					alerts.push({ tone: "positive", text: `${name}: Chi phí giảm mạnh ${formatPercent(costDelta)}.` });
				} else if (costDelta >= 10) {
					alerts.push({ tone: "negative", text: `${name}: Chi phí tăng ${formatPercent(costDelta)}.` });
				}
				return;
			}

			if (revenueDelta >= 20 || revenueYoY >= 20) {
				alerts.push({ tone: "positive", text: `${name}: Doanh thu tăng tốt (${formatPercent(revenueDelta)}).` });
			}
			if (revenueDelta <= -10 || revenueYoY <= -10) {
				alerts.push({ tone: "negative", text: `${name}: Doanh thu giảm (${formatPercent(revenueDelta)}).` });
			}
		});

		if (plan && plan.totals) {
			const delta = calcPercent(actual.totals.profit_ytd, plan.totals.profit_ytd);
			if (delta >= 0) {
				alerts.push({ tone: "positive", text: `LNTT đang đạt ${formatPercent(delta)} so với kế hoạch.` });
			} else {
				alerts.push({ tone: "negative", text: `LNTT thấp hơn kế hoạch ${formatPercent(delta)}.` });
			}
		} else if (actual.totals) {
			const yoy = calcPercent(actual.totals.profit_ytd, actual.totals.profit_prev_ytd);
			if (yoy >= 10) {
				alerts.push({ tone: "positive", text: `LNTT tăng ${formatPercent(yoy)} so với cùng kỳ.` });
			} else if (yoy <= -10) {
				alerts.push({ tone: "negative", text: `LNTT giảm ${formatPercent(yoy)} so với cùng kỳ.` });
			}
		}

		const html =
			alerts.length === 0
				? `<div class="growth-alert neutral">Không có cảnh báo nổi bật.</div>`
				: alerts.map((alert) => `<div class="growth-alert ${alert.tone}">${alert.text}</div>`).join("");
		this.$wrapper.find('[data-key="alerts"]').html(html);
	}

	renderTrend(trends) {
		if (!trends) {
			return;
		}
		const categories = trends.months || [];
		const revenue = trends.revenue || [];
		const profit = trends.profit || [];
		this.charts.trend = Highcharts.chart("growth-trend-chart", {
			chart: { zoomType: "xy" },
			title: { text: "" },
			xAxis: [{ categories }],
			yAxis: [
				{ title: { text: "Doanh thu" } },
				{ title: { text: "LNTT" }, opposite: true },
			],
			series: [
				{ type: "column", name: "Doanh thu", data: revenue },
				{ type: "spline", name: "LNTT", data: profit, yAxis: 1 },
			],
		});
	}

	renderWaterfall(groups) {
		if (!groups || !groups.length) {
			return;
		}
		const groupMap = {};
		groups.forEach((g) => {
			groupMap[g.name] = g.profit_ytd || 0;
		});
		const data = [
			{ name: "Nhóm I", y: groupMap["Nhóm 1"] || 0 },
			{ name: "Nhóm II", y: groupMap["Nhóm 2"] || 0 },
			{ name: "Nhóm III", y: groupMap["Nhóm 3"] || 0 },
			{ name: "Nhóm IV", y: -(groupMap["Nhóm 4"] || 0) },
			{ name: "Tổng LNTT", isSum: true },
		];
		this.charts.waterfall = Highcharts.chart("growth-waterfall-chart", {
			chart: { type: "waterfall" },
			title: { text: "" },
			legend: { enabled: false },
			xAxis: { type: "category" },
			yAxis: { title: { text: "LNTT" } },
			series: [
				{
					upColor: "#22C55E",
					color: "#EF4444",
					data,
					dataLabels: { enabled: true, format: "{point.y:,.0f}" },
				},
			],
		});
	}

	renderGroup1(items, planItems) {
		if (!window.Highcharts) {
			setChartPlaceholder("growth-group1-treemap", "Chưa tải Highcharts.");
			setChartPlaceholder("growth-group1-bar", "Chưa tải Highcharts.");
			setChartPlaceholder("growth-group1-donut", "Chưa tải Highcharts.");
			return;
		}
		const data = (items || []).map((item) => ({
			name: item.name,
			value: item.revenue_ytd || 0,
			colorValue: item.profit_ytd || 0,
		}));
		if (!data.length) {
			setChartPlaceholder("growth-group1-treemap", "Chưa có dữ liệu Nhóm I.");
		} else if (!Highcharts.seriesTypes.treemap) {
			setChartPlaceholder("growth-group1-treemap", "Thiếu module Treemap.");
		} else {
			try {
				this.charts.group1Treemap = Highcharts.chart("growth-group1-treemap", {
					series: [
						{
							type: "treemap",
							layoutAlgorithm: "squarified",
							colorByPoint: true,
							dataLabels: { enabled: true, format: "{point.name}" },
							data,
						},
					],
					title: { text: "" },
				});
			} catch (err) {
				setChartPlaceholder("growth-group1-treemap", "Không thể hiển thị Treemap.");
			}
		}

		const categories = (items || []).map((item) => item.name);
		const actualValues = (items || []).map((item) => item.profit_ytd || 0);
		const planValues = (planItems || []).map((item) => item.profit_ytd || 0);
		const series = [
			{ type: "bar", name: "Thực tế", data: actualValues },
		];
		if (planItems && planItems.length) {
			series.push({
				type: "spline",
				name: "Kế hoạch",
				data: planValues,
				dashStyle: "Dash",
				color: "#F97316",
			});
		}

		if (!categories.length) {
			setChartPlaceholder("growth-group1-bar", "Chưa có dữ liệu Nhóm I.");
		} else {
			try {
				this.charts.group1Bar = Highcharts.chart("growth-group1-bar", {
					chart: { type: "bar" },
					title: { text: "" },
					xAxis: { categories },
					yAxis: { title: { text: "LNTT lũy kế" } },
					series,
				});
			} catch (err) {
				setChartPlaceholder("growth-group1-bar", "Không thể hiển thị biểu đồ.");
			}
		}

		const donutData = (items || []).slice(0, 4).map((item) => ({
			name: item.name,
			y: item.profit_ytd || 0,
		}));
		if (!donutData.length) {
			setChartPlaceholder("growth-group1-donut", "Chưa có dữ liệu Nhóm I.");
		} else {
			try {
				this.charts.group1Donut = Highcharts.chart("growth-group1-donut", {
					chart: { type: "pie" },
					title: { text: "" },
					plotOptions: { pie: { innerSize: "65%", dataLabels: { enabled: true, format: "{point.name}" } } },
					series: [{ name: "LNTT", data: donutData }],
				});
			} catch (err) {
				setChartPlaceholder("growth-group1-donut", "Không thể hiển thị Donut.");
			}
		}
	}

	renderGroup2(items) {
		const html = (items || []).slice(0, 2).map((item) => {
			return `
				<div class="growth-kpi-tile">
					<h4>${escape(item.name)}</h4>
					<div class="growth-kpi-value">${formatNumber(item.revenue_ytd || 0)}</div>
					<p>LNTT: ${formatNumber(item.profit_ytd || 0)}</p>
				</div>
			`;
		});
		this.$wrapper.find('[data-key="group2_kpis"]').html(html.join("") || "<div>Chưa có dữ liệu.</div>");
	}

	renderGroup3(items) {
		if (!window.Highcharts) {
			setChartPlaceholder("growth-group3-bar", "Chưa tải Highcharts.");
			return;
		}
		const categories = (items || []).map((item) => item.name);
		const values = (items || []).map((item) => item.profit_ytd || 0);
		if (!categories.length) {
			setChartPlaceholder("growth-group3-bar", "Chưa có dữ liệu Nhóm III.");
			return;
		}
		try {
			this.charts.group3Bar = Highcharts.chart("growth-group3-bar", {
				chart: { type: "column" },
				title: { text: "" },
				xAxis: { categories },
				yAxis: { title: { text: "LNTT" } },
				series: [{ name: "LNTT", data: values }],
			});
		} catch (err) {
			setChartPlaceholder("growth-group3-bar", "Không thể hiển thị biểu đồ.");
		}
	}

	renderInvestment(items) {
		if (!window.Highcharts) {
			setChartPlaceholder("growth-investment-waterfall", "Chưa tải Highcharts.");
			return;
		}
		const data = (items || []).map((item) => ({
			name: item.name,
			y: item.profit_ytd || 0,
		}));
		if (!data.length) {
			setChartPlaceholder("growth-investment-waterfall", "Chưa có dữ liệu đầu tư.");
			return;
		}
		if (!Highcharts.seriesTypes.waterfall) {
			setChartPlaceholder("growth-investment-waterfall", "Thiếu module Waterfall.");
			return;
		}
		data.push({ name: "Tổng LNTT", isSum: true });
		try {
			this.charts.investment = Highcharts.chart("growth-investment-waterfall", {
				chart: { type: "waterfall" },
				title: { text: "" },
				legend: { enabled: false },
				xAxis: { type: "category" },
				series: [
					{
						upColor: "#22C55E",
						color: "#EF4444",
						data,
						dataLabels: { enabled: true, format: "{point.y:,.0f}" },
					},
				],
			});
		} catch (err) {
			setChartPlaceholder("growth-investment-waterfall", "Không thể hiển thị Waterfall.");
		}
	}

	renderCost(costTrend, groups, planGroups) {
		const categories = (costTrend || []).map((_, idx) => `T${String(idx + 1).padStart(2, "0")}`);
		this.charts.cost = Highcharts.chart("growth-cost-line", {
			chart: { type: "areaspline" },
			title: { text: "" },
			xAxis: { categories },
			yAxis: { title: { text: "Chi phí" } },
			series: [{ name: "Chi phí vận hành", data: costTrend || [] }],
		});

		const actualCost = (groups || []).find((g) => g.name === "Nhóm 4");
		const planCost = (planGroups || []).find((g) => g.name === "Nhóm 4");
		const actualValue = actualCost?.cost_ytd || 0;
		const planValue = planCost?.cost_ytd || actualValue || 1;
		const ratio = planValue ? (actualValue / planValue) * 100 : 0;

		this.charts.gauge = Highcharts.chart("growth-cost-gauge", {
			chart: { type: "solidgauge" },
			title: { text: "" },
			pane: { startAngle: -90, endAngle: 90, background: [{ outerRadius: "100%", innerRadius: "80%", shape: "arc" }] },
			yAxis: {
				min: 0,
				max: 140,
				stops: [
					[0.6, "#22C55E"],
					[0.9, "#F97316"],
					[1.1, "#EF4444"],
				],
				lineWidth: 0,
				tickWidth: 0,
				labels: { enabled: false },
			},
			series: [
				{
					name: "Chi phí",
					data: [ratio],
					dataLabels: {
						format: `<div style="text-align:center"><span style="font-size:20px">{y:.0f}%</span><br/><span style="font-size:12px">so với KH</span></div>`,
					},
				},
			],
		});

		const forecast = planValue || actualValue;
		this.$wrapper.find('[data-key="cost_forecast"]').html(`
			<div class="growth-forecast-card">
				<h4>${formatNumber(actualValue)}</h4>
				<p>Dự kiến / Kế hoạch: ${formatNumber(forecast)}</p>
			</div>
		`);
	}
}

function formatNumber(value) {
	if (value === null || value === undefined) {
		return "0";
	}
	return frappe.format_number ? frappe.format_number(value, null, 0) : new Intl.NumberFormat("vi-VN").format(value);
}

function renderDelta(current, previous, label) {
	if (!previous) {
		return `${label}: -`;
	}
	const delta = calcPercent(current, previous);
	return `${label}: ${formatPercent(delta)}`;
}

function calcPercent(current, previous) {
	if (!previous) {
		return 0;
	}
	return ((current - previous) / Math.abs(previous)) * 100;
}

function formatPercent(value) {
	if (value === null || value === undefined) {
		return "0%";
	}
	return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function escape(value) {
	return frappe.utils.escape_html(value || "");
}

function setChartPlaceholder(containerId, message) {
	const container = document.getElementById(containerId);
	if (!container) {
		return;
	}
	container.innerHTML = `<div class="growth-chart-placeholder">${message}</div>`;
}

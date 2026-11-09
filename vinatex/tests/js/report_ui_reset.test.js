/* Kiểm tra bản vá dọn giao diện của trang query-report.
 * Chạy: node vinatex/tests/js/report_ui_reset.test.js
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SCRIPT_PATH = path.join(__dirname, "..", "..", "public", "js", "report_ui_reset.js");
const CUSTOM_UI_SELECTOR = "[data-vnt-report-ui]";

let failures = 0;

async function test(name, fn) {
	try {
		await fn();
		console.log(`  ✓ ${name}`);
	} catch (error) {
		failures += 1;
		console.log(`  ✗ ${name}`);
		console.log(`    ${error && error.message}`);
	}
}

function load_script() {
	const source = fs.readFileSync(SCRIPT_PATH, "utf8");
	vm.runInThisContext(source, { filename: SCRIPT_PATH });
}

function make_element(log, label) {
	const element = {
		empty() {
			log.push(`${label}.empty`);
			return element;
		},
		hide() {
			log.push(`${label}.hide`);
			return element;
		},
		remove() {
			log.push(`${label}.remove`);
			return element;
		},
	};
	return element;
}

function make_main(log, class_attr) {
	let class_names = class_attr;
	const found = {
		remove() {
			log.push("custom.remove");
		},
	};
	return {
		last_selector: null,
		find(selector) {
			this.last_selector = selector;
			return found;
		},
		attr(name) {
			return name === "class" ? class_names : undefined;
		},
		removeClass(names) {
			const removed = String(names || "").split(/\s+/).filter(Boolean);
			class_names = class_names
				.split(/\s+/)
				.filter((name) => name && !removed.includes(name))
				.join(" ");
			return this;
		},
		classes() {
			return class_names;
		},
	};
}

// Lớp giả thay cho frappe.views.QueryReport; trả về một "proto" để kiểm tra việc vá.
function stub_query_report(log, original_result) {
	const calls = { load_report: 0, args: null, self: null };
	class QueryReport {
		load_report(...args) {
			log.push("original");
			calls.load_report += 1;
			calls.args = args;
			calls.self = this;
			return original_result;
		}
		refresh() {}
	}
	global.frappe = { views: { QueryReport } };
	return { proto: QueryReport.prototype, calls };
}

function make_report(proto, log, class_attr) {
	const main = make_main(log, class_attr);
	const report = Object.create(proto);
	report.$status = make_element(log, "status");
	report.$report = make_element(log, "report");
	report.page = { main };
	return { report, main };
}

// Báo cáo chuẩn của Frappe còn có biểu đồ, thẻ tóm tắt và dòng footer thời gian chạy.
function make_full_report(proto, log, class_attr) {
	const { report, main } = make_report(proto, log, class_attr);
	report.$summary = make_element(log, "summary");
	report.$chart = make_element(log, "chart");
	report.$report_footer = make_element(log, "footer");
	return { report, main };
}

async function main() {
	console.log("report_ui_reset");

	await test("dọn $status, $report, phần tử đánh dấu và class chế độ trước khi gọi bản gốc", () => {
		const log = [];
		const { proto } = stub_query_report(log);
		load_script();
		const { report, main: page_main } = make_report(
			proto,
			log,
			"layout-main-section vnt-keep-me vnt-attendance-html-mode"
		);

		report.load_report();

		assert.deepEqual(log, ["status.empty", "status.hide", "report.empty", "custom.remove", "original"]);
		assert.equal(page_main.classes(), "layout-main-section vnt-keep-me");
		assert.equal(page_main.last_selector, CUSTOM_UI_SELECTOR);
	});

	await test("gọi bản gốc với đúng this, tham số và trả về giá trị của bản gốc", () => {
		const log = [];
		const { proto, calls } = stub_query_report(log, "ket-qua-goc");
		load_script();
		const { report } = make_report(proto, log, "layout-main-section");

		const result = report.load_report({ employee: "HR-EMP-0001" });

		assert.equal(result, "ket-qua-goc");
		assert.equal(calls.load_report, 1);
		assert.deepEqual(calls.args, [{ employee: "HR-EMP-0001" }]);
		assert.equal(calls.self, report);
	});

	await test("không ném lỗi khi $status/$report/page chưa tồn tại", () => {
		const log = [];
		const { proto, calls } = stub_query_report(log);
		load_script();
		const report = Object.create(proto);

		assert.doesNotThrow(() => report.load_report());
		assert.equal(calls.load_report, 1);
	});

	await test("nạp script hai lần không vá chồng", () => {
		const log = [];
		const { proto, calls } = stub_query_report(log);
		load_script();
		load_script();
		const { report } = make_report(proto, log, "layout-main-section");

		report.load_report();

		assert.equal(calls.load_report, 1);
		assert.deepEqual(
			log.filter((entry) => entry === "report.empty"),
			["report.empty"]
		);
	});

	await test("không đụng tới refresh", () => {
		const log = [];
		const { proto } = stub_query_report(log);
		const original_refresh = proto.refresh;
		load_script();

		assert.equal(proto.refresh, original_refresh);
	});

	await test("chờ tới khi frappe.views.QueryReport tồn tại rồi mới vá", async () => {
		const log = [];
		global.frappe = {};
		load_script();

		const { proto, calls } = stub_query_report(log);
		const original_load_report = proto.load_report;
		await new Promise((resolve) => setTimeout(resolve, 400));

		assert.equal(typeof proto.load_report, "function");
		assert.notEqual(proto.load_report, original_load_report);

		const { report } = make_report(proto, log, "layout-main-section vnt-attendance-html-mode");
		report.load_report();
		assert.equal(calls.load_report, 1);
		assert.deepEqual(log, ["status.empty", "status.hide", "report.empty", "custom.remove", "original"]);
	});

	await test("dọn cả $summary, $chart và footer thời gian chạy của báo cáo trước", () => {
		const log = [];
		const { proto } = stub_query_report(log);
		load_script();
		const { report } = make_full_report(proto, log, "layout-main-section vnt-attendance-html-mode");

		report.load_report();

		assert.deepEqual(log, [
			"status.empty",
			"status.hide",
			"report.empty",
			"summary.empty",
			"chart.empty",
			"footer.remove",
			"custom.remove",
			"original",
		]);
	});

	await test("không đốt cờ khi load_report chưa phải là hàm", () => {
		const log = [];
		class QueryReport {
			refresh() {}
		}
		global.frappe = { views: { QueryReport } };
		load_script();

		// Frappe thật gắn load_report vào cùng prototype sau đó; lần nạp sau phải vá được.
		let original_calls = 0;
		QueryReport.prototype.load_report = function () {
			original_calls += 1;
			return "ket-qua-goc";
		};
		load_script();

		const report = Object.create(QueryReport.prototype);
		report.$report = make_element(log, "report");

		assert.equal(report.load_report(), "ket-qua-goc");
		assert.equal(original_calls, 1);
		assert.deepEqual(log, ["report.empty"]);
	});

	if (failures) {
		console.log(`\n${failures} test thất bại`);
		process.exit(1);
	}
	console.log("\nTất cả test đạt");
}

main();

/* Hợp đồng với report_ui_reset.js: mọi giao diện tự dựng của báo cáo phải mang
 * data-vnt-report-ui, nếu không nó sẽ nằm lại trên màn hình khi đổi báo cáo.
 * Test tự quét thư mục report nên báo cáo mới thêm sau này cũng bị soi.
 * Chạy: node vinatex/tests/js/report_ui_markers.test.js
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const REPORT_DIR = path.join(__dirname, "..", "..", "vnt_hr", "report");
const MARKER = "data-vnt-report-ui";

// Chèn ra ngoài $report thì datatable dựng lại không ghi đè được -> bắt buộc đánh dấu.
const OUTSIDE_REPORT_CALLS = [
	"insertAfter(report.$report)",
	"insertAfter(this.$report)",
	"appendTo(report.page.main)",
	"appendTo(this.page.main)",
];

// Phần tử gốc của ba giao diện tự dựng hiện có.
const ROOT_CLASSES = [
	"vnt-attendance-matrix-wrapper",
	"vnt-monthly-report",
	"vnt-overtime-report",
];

let failures = 0;

function test(name, fn) {
	try {
		fn();
		console.log(`  ✓ ${name}`);
	} catch (error) {
		failures += 1;
		console.log(`  ✗ ${name}`);
		console.log(`    ${error && error.message}`);
	}
}

// Câu lệnh chèn: từ dấu kết thúc lệnh trước đó tới hết lời gọi chèn.
function find_unmarked_insertions(source) {
	const violations = [];
	for (const call of OUTSIDE_REPORT_CALLS) {
		let index = source.indexOf(call);
		while (index !== -1) {
			const start = Math.max(
				source.lastIndexOf(";", index),
				source.lastIndexOf("{", index),
				source.lastIndexOf("}", index)
			);
			const statement = source.slice(start + 1, index + call.length);
			if (!statement.includes(MARKER)) {
				violations.push(statement.trim());
			}
			index = source.indexOf(call, index + 1);
		}
	}
	return violations;
}

function tag_with_class(source, class_name) {
	const tags = source.match(/<[a-zA-Z][^<>]*>/g) || [];
	return tags.find((tag) => tag.includes(class_name)) || null;
}

function report_scripts() {
	return fs
		.readdirSync(REPORT_DIR, { withFileTypes: true })
		.filter((entry) => entry.isDirectory())
		.flatMap((entry) =>
			fs
				.readdirSync(path.join(REPORT_DIR, entry.name))
				.filter((file) => file.endsWith(".js"))
				.map((file) => path.join(entry.name, file))
		);
}

console.log("report_ui_markers");

test("phát hiện phần tử chèn ngoài $report mà thiếu dấu", () => {
	const source = `report.$vnt = $('<div class="vnt-x"></div>').insertAfter(report.$report);`;
	assert.deepEqual(find_unmarked_insertions(source).length, 1);
});

test("chấp nhận dấu đặt trước class và dùng nháy đơn", () => {
	const source = `report.$vnt = $("<div data-vnt-report-ui class='vnt-x'></div>").insertAfter(report.$report);`;
	assert.deepEqual(find_unmarked_insertions(source), []);
});

const scripts = report_scripts();

test(`quét được các file report (${scripts.length} file)`, () => {
	assert.ok(scripts.length >= 3, `chỉ tìm thấy ${scripts.length} file`);
});

test("không file report nào chèn ra ngoài $report mà thiếu dấu", () => {
	const violations = scripts.flatMap((relative_path) =>
		find_unmarked_insertions(
			fs.readFileSync(path.join(REPORT_DIR, relative_path), "utf8")
		).map((statement) => `${relative_path}: ${statement}`)
	);
	assert.deepEqual(violations, []);
});

for (const class_name of ROOT_CLASSES) {
	test(`phần tử gốc .${class_name} mang ${MARKER}`, () => {
		const found = scripts
			.map((relative_path) => fs.readFileSync(path.join(REPORT_DIR, relative_path), "utf8"))
			.map((source) => tag_with_class(source, class_name))
			.find(Boolean);
		assert.ok(found, `không tìm thấy thẻ nào mang class ${class_name}`);
		assert.ok(found.includes(MARKER), `thẻ gốc thiếu ${MARKER}: ${found}`);
	});
}

if (failures) {
	console.log(`\n${failures} test thất bại`);
	process.exit(1);
}
console.log("\nTất cả test đạt");

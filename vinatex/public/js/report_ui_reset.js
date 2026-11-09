/* Trang query-report dùng chung một instance frappe.query_report, nên khi đổi
 * báo cáo thì $status, các phần tử tự dựng và class chế độ hiển thị của báo cáo
 * trước vẫn còn trên màn hình cho tới khi dữ liệu mới về. Dọn ngay đầu
 * load_report (chỉ chạy khi đổi báo cáo) để báo cáo mới bắt đầu tải là sạch.
 */
(() => {
	const PATCH_FLAG = "_vnt_report_ui_reset_patched";
	const CUSTOM_UI_SELECTOR = "[data-vnt-report-ui]";
	const MODE_CLASS_SUFFIX = "-html-mode";

	const reset_report_ui = (report) => {
		if (!report) {
			return;
		}

		if (report.$status) {
			report.$status.empty().hide();
		}

		if (report.$report) {
			report.$report.empty();
		}

		// Biểu đồ và thẻ tóm tắt chỉ được làm rỗng trong refresh(), còn dòng footer
		// ("Execution Time" của báo cáo trước) sống tới tận cuối lần tải mới.
		if (report.$summary) {
			report.$summary.empty();
		}

		if (report.$chart) {
			report.$chart.empty();
		}

		if (report.$report_footer) {
			report.$report_footer.remove();
		}

		const main = report.page && report.page.main;
		if (!main) {
			return;
		}

		// Giao diện tự dựng nằm ngoài $report tự khai báo bằng data-vnt-report-ui.
		main.find(CUSTOM_UI_SELECTOR).remove();

		const stale_modes = String(main.attr("class") || "")
			.split(/\s+/)
			.filter((name) => name.endsWith(MODE_CLASS_SUFFIX));
		if (stale_modes.length) {
			main.removeClass(stale_modes.join(" "));
		}
	};

	const patch_query_report = () => {
		if (!frappe?.views?.QueryReport) {
			// Retry after core assets are ready.
			setTimeout(patch_query_report, 200);
			return;
		}

		const proto = frappe.views.QueryReport.prototype;
		if (proto[PATCH_FLAG]) {
			return;
		}

		const original_load_report = proto.load_report;
		if (typeof original_load_report !== "function") {
			// Bản Frappe sau này đổi tên hàm: không đặt cờ để còn vá lại được.
			return;
		}
		proto[PATCH_FLAG] = true;

		proto.load_report = function () {
			reset_report_ui(this);
			return original_load_report.apply(this, arguments);
		};
	};

	patch_query_report();
})();

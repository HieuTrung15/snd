(() => {
	const patch_query_report = () => {
		if (!frappe?.views?.QueryReport) {
			// Retry after core assets are ready.
			setTimeout(patch_query_report, 200);
			return;
		}

		const proto = frappe.views.QueryReport.prototype;
		if (proto._vnt_hide_actions_patched) {
			return;
		}
		proto._vnt_hide_actions_patched = true;

		const original_setup_page_head = proto.setup_page_head;

		const toggle_actions_button = (page, should_hide) => {
			if (!page) {
				return;
			}

			if (!page._vnt_original_show_actions_menu) {
				page._vnt_original_show_actions_menu = page.show_actions_menu;
				page._vnt_original_hide_actions_menu = page.hide_actions_menu;
			}

			if (should_hide) {
				page.hide_actions_menu();
				page.show_actions_menu = function () {
					this.actions_btn_group.addClass("hide");
				};
				page.hide_actions_menu = function () {
					this.actions_btn_group.addClass("hide");
				};
			} else {
				if (page._vnt_original_show_actions_menu) {
					page.show_actions_menu = page._vnt_original_show_actions_menu;
				}
				if (page._vnt_original_hide_actions_menu) {
					page.hide_actions_menu = page._vnt_original_hide_actions_menu;
				}
			}
		};

		proto.setup_page_head = function (...args) {
			if (original_setup_page_head) {
				original_setup_page_head.apply(this, args);
			}

			const is_script_report = this.report_doc?.report_type === "Script Report";
			toggle_actions_button(this.page, is_script_report);
		};
	};

	if (window?.frappe) {
		patch_query_report();
	} else {
		$(document).ready(patch_query_report);
	}
})();

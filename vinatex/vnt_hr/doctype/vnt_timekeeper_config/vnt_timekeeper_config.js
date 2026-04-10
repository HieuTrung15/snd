// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Timekeeper Config", {
	refresh(frm) {
        frm.add_custom_button(__('Đồng bộ dữ liệu chấm công'), function() {
			frappe.call({
				method: "vinatex.vinatex.doctype.overrides.timekeeping.sync_timekeeper_data",
			});
		});
	}
});

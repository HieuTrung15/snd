// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timekeeper Config", {
	refresh(frm) {
        frm.add_custom_button(__('Đồng bộ dữ liệu chấm công'), function() {
			frappe.call({
				method: "vinatex.vinatex.doctype.overrides.timekeeping.create_allocation_nghi_con_ket_hon",
			});
		});
	}
});

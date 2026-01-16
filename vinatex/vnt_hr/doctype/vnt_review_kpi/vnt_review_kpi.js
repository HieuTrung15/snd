// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

const load_review_tasks = (frm) => {
	const employee = frm.doc.employee;
	const period = frm.doc.chuky;
	const detail = frm.doc.chi_tiet_ky_review;

	if (!employee || !period || !detail) {
		return;
	}

	const fetch_items = () => {
		frappe.call({
			method: "vinatex.vnt_hr.doctype.vnt_review_kpi.vnt_review_kpi.get_review_tasks",
			args: {
				employee: employee,
				chuky: period,
				chi_tiet_ky_review: detail,
				review_date: frm.doc.date,
			},
			freeze: true,
			freeze_message: __("Đang tải danh sách công việc..."),
			callback: (r) => {
				const payload = r.message || {};
				const items = Array.isArray(payload.items) ? payload.items : [];

				frm.clear_table("items");
				items.forEach((item) => {
					const row = frm.add_child("items");
					row.congviec = item.congviec;
				});

				frm.refresh_field("items");

				if (!items.length && payload.start_date && payload.end_date) {
					frappe.msgprint(
						__("Không tìm thấy công việc trong khoảng {0} đến {1}.", [
							payload.start_date,
							payload.end_date,
						])
					);
				}
			},
		});
	};

	if (frm.doc.items && frm.doc.items.length) {
		frappe.confirm(
			__("Bạn có muốn lấy lại danh sách công việc theo kỳ review đã chọn?"),
			() => {
				fetch_items();
			},
			() => {}
		);
	} else {
		fetch_items();
	}
};

frappe.ui.form.on("VNT Review KPI", {
	employee(frm) {
		load_review_tasks(frm);
	},
	chuky(frm) {
		load_review_tasks(frm);
	},
	chi_tiet_ky_review(frm) {
		load_review_tasks(frm);
	},
	date(frm) {
		load_review_tasks(frm);
	},
});

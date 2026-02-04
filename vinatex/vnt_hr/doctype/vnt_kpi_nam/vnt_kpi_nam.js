// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT KPI Nam", {
	type(frm) {
		if (frm.doc.type !== "Điều chỉnh" && frm.doc.reference_kpi_nam) {
			frm.set_value("reference_kpi_nam", null);
		}
	},
	reference_kpi_nam(frm) {
		if (!frm.doc.reference_kpi_nam || frm.doc.type !== "Điều chỉnh") {
			return;
		}

		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "VNT KPI Nam",
				name: frm.doc.reference_kpi_nam,
			},
		}).then((r) => {
			const source = r.message;
			if (!source) {
				return;
			}
			if (!frm.doc.kpi_name) {
				frm.set_value("kpi_name", source.kpi_name);
			}
			frm.set_value("kpi_year", source.kpi_year);
			frm.set_value("department", source.department);
		});
	},
	refresh(frm) {
		frm.set_query("reference_kpi_nam", () => {
			const filters = {
				docstatus: 1,
				type: ["!=", "Điều chỉnh"],
			};
			if (frm.doc.kpi_year) {
				filters.kpi_year = frm.doc.kpi_year;
			}
			if (frm.doc.department) {
				filters.department = frm.doc.department;
			}
			return { filters };
		});

		// nếu trường employee trống thì sẽ tìm đến employee của user hiện tại đang tạo phiếu
		if (!frm.doc.employee) {
			frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then((r) => {
				if (r.message) {
					frm.set_value("employee", r.message.name);
				}
			});
		}
		//nếu trường date trống thì sẽ tự động điền ngày hiện tại
		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}
		//nếu trường kpi_year trống thì tự động điền năm hiện tại
		if (!frm.doc.kpi_year) {
			frm.set_value("kpi_year", frappe.datetime.get_today().substr(0, 4));
		}
	},
});

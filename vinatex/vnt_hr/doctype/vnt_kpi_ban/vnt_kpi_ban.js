// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

const load_kpi_nam_items = (frm) => {
	const kpiYear = frm.doc.kpi_year;
	const department = frm.doc.department;
	const type = frm.doc.type;

	if (!kpiYear || !department || !type || type === "Điều chỉnh") {
		return;
	}

	const fetchItems = () => {
		frappe.call({
			method: "vinatex.vnt_hr.doctype.vnt_kpi_nam.vnt_kpi_nam.get_effective_kpi_nam_items",
			args: {
				kpi_year: kpiYear,
				department: department,
				business_type: type,
			},
			freeze: true,
			freeze_message: __("Đang tải KPI Năm..."),
		}).then((r) => {
			const payload = r.message || {};
			const rows = payload.items || [];
			if (!rows.length) {
				frappe.msgprint(
					__("Không tìm thấy KPI Năm hiệu lực cho năm {0}, ban {1}.", [
						kpiYear,
						department,
					])
				);
				return;
			}

			frm.clear_table("items");
			rows.forEach((item) => {
				const row = frm.add_child("items");
				row.vnt_kpi_nam = item.name;
				row.kpi_details = item.kpi_name;
			});
			frm.refresh_field("items");
		});
	};

	if (frm.doc.items && frm.doc.items.length) {
		frappe.confirm(
			__("Bạn có muốn lấy dữ liệu KPI Năm tự động?"),
			() => fetchItems(),
			() => {}
		);
	} else {
		fetchItems();
	}
};

const load_reference_kpi_ban_items = (frm) => {
	if (frm.doc.type !== "Điều chỉnh" || !frm.doc.reference_kpi_ban) {
		return;
	}

	const fetchItems = () => {
		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "VNT KPI Ban",
				name: frm.doc.reference_kpi_ban,
			},
		}).then((r) => {
			const source = r.message;
			if (!source) {
				return;
			}

			frm.set_value("kpi_year", source.kpi_year);
			frm.set_value("department", source.department);

			frm.clear_table("items");
			(source.items || []).forEach((item) => {
				const row = frm.add_child("items");
				row.vnt_kpi_nam = item.vnt_kpi_nam;
				row.kpi_details = item.kpi_details;
				row.percent = item.percent;
				row.date = item.date;
				row.note = item.note;
			});
			frm.refresh_field("items");
		});
	};

	if (frm.doc.items && frm.doc.items.length) {
		frappe.confirm(
			__("Bạn có muốn lấy dữ liệu từ phiếu KPI Ban tham chiếu?"),
			() => fetchItems(),
			() => {}
		);
	} else {
		fetchItems();
	}
};

frappe.ui.form.on("VNT KPI Ban", {
	kpi_year(frm) {
		load_kpi_nam_items(frm);
	},
	department(frm) {
		load_kpi_nam_items(frm);
	},
	type(frm) {
		if (frm.doc.type !== "Điều chỉnh" && frm.doc.reference_kpi_ban) {
			frm.set_value("reference_kpi_ban", null);
		}
		load_kpi_nam_items(frm);
	},
	reference_kpi_ban(frm) {
		load_reference_kpi_ban_items(frm);
	},
	refresh(frm) {
		frm.set_query("reference_kpi_ban", () => {
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

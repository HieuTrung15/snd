(() => {
	// Giải mã và hiển thị đúng tong_thu_nhap, thuc_linh trên List View
	const DOC = "VNT Salary Slip";

	frappe.listview_settings[DOC] = Object.assign({}, frappe.listview_settings[DOC] || {}, {
		add_fields: ["tong_thu_nhap", "thuc_linh", "tong_thu_nhap_encrypted", "thuc_linh_encrypted"],
		refresh(listview) {
			const rows = listview?.data || [];
			if (!rows.length || listview._vntDecrypting) {
				return;
			}

			const names = rows
				.filter((row) => row.name && (row.tong_thu_nhap_encrypted || row.thuc_linh_encrypted))
				.map((row) => row.name);

			if (!names.length) {
				return;
			}

			listview._vntDecrypting = true;
			frappe
				.call({
					method: "vinatex.vnt_hr.doctype.vnt_salary_slip.vnt_salary_slip.get_decrypted_salary_for_list",
					args: { names },
				})
				.then((r) => {
					const payload = r?.message || {};
					if (!Object.keys(payload).length) {
						return;
					}

					listview.data = rows.map((row) => {
						const values = payload[row.name];
						if (values) {
							row.tong_thu_nhap = values.tong_thu_nhap;
							row.thuc_linh = values.thuc_linh;
						}
						return row;
					});

					// render lại với giá trị đã giải mã
					listview.render();
				})
				.finally(() => {
					listview._vntDecrypting = false;
				});
		},
	});
})();

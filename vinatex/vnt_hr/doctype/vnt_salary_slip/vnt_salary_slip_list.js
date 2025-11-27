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

			const needDecrypt = rows.filter((row) => {
				if (!row.name) return false;
				const hasCipher = row.tong_thu_nhap_encrypted || row.thuc_linh_encrypted;
				if (!hasCipher) return false;
				// Bỏ qua nếu đã có số khác 0
				const gross = Number(row.tong_thu_nhap || 0);
				const net = Number(row.thuc_linh || 0);
				return gross === 0 || net === 0;
			});

			const names = needDecrypt.map((row) => row.name);

			if (!names.length) {
				return;
			}

			listview._vntDecrypting = true;
			const chunkSize = 50;
			const chunks = [];
			for (let i = 0; i < names.length; i += chunkSize) {
				chunks.push(names.slice(i, i + chunkSize));
			}

			const mergePayload = {};

			const fetchChunk = (chunk) =>
				frappe
					.call({
						method: "vinatex.vnt_hr.doctype.vnt_salary_slip.vnt_salary_slip.get_decrypted_salary_for_list",
						args: { names: chunk },
					})
					.then((r) => {
						Object.assign(mergePayload, r?.message || {});
					});

			frappe
				.run_serially(chunks.map((c) => () => fetchChunk(c)))
				.then(() => {
					if (!Object.keys(mergePayload).length) {
						return;
					}
					listview.data = rows.map((row) => {
						const values = mergePayload[row.name];
						if (values) {
							row.tong_thu_nhap = values.tong_thu_nhap;
							row.thuc_linh = values.thuc_linh;
						}
						return row;
					});
					listview.render();
				})
				.finally(() => {
					listview._vntDecrypting = false;
				});
		},
	});
})();

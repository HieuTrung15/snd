// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Timekeeper Config", {
	refresh(frm) {
		frm.add_custom_button(__('Đồng bộ dữ liệu chấm công'), function () {
			frappe.call({
				method: "vinatex.vinatex.doctype.overrides.timekeeping.sync_timekeeper_data",
			});
		});

		frm.add_custom_button(__('Test kết nối'), function () {
			if (frm.is_new()) {
				frappe.msgprint(__('Hãy lưu thiết bị trước khi test.'));
				return;
			}
			frappe.dom.freeze(__('Đang test ') + frm.doc.name + ' ...');
			frappe.call({
				method: "vinatex.vinatex.doctype.overrides.timekeeping.test_device_connection",
				args: { config_name: frm.doc.name, timeout: 60 },
				always: () => frappe.dom.unfreeze(),
				callback: (r) => {
					const res = (r.message || [])[0];
					if (!res) { frappe.msgprint(__('Không có kết quả.')); return; }
					const row = (k, v) => `<tr><td style="padding:4px 10px;color:#687178">${k}</td><td style="padding:4px 10px"><b>${v ?? '-'}</b></td></tr>`;
					const ok = (b) => b ? '<span style="color:#16a34a">OK</span>' : '<span style="color:#dc2626">FAIL</span>';
					frappe.msgprint({
						title: __('Kết quả test') + ': ' + res.name,
						indicator: res.zk_ok ? 'green' : 'red',
						message: `<table style="width:100%;border-collapse:collapse">
							${row('IP / Port', `${res.ip} : ${res.port}`)}
							${row('DNS resolve', res.dns_ip)}
							${row('TCP', `${ok(res.tcp_ok)} (${res.tcp_ms} ms)`)}
							${row('ZK connect', `${ok(res.zk_ok)} (${res.zk_ms} ms)`)}
							${row('Firmware', res.firmware)}
							${row('Serial', res.serial)}
							${row('Số log trên máy', res.log_count)}
							${res.error ? row('Lỗi', `<span style="color:#dc2626">${frappe.utils.escape_html(res.error)}</span>`) : ''}
						</table>`
					});
				}
			});
		});

		frm.add_custom_button(__('Test tất cả thiết bị'), function () {
			frappe.dom.freeze(__('Đang test tất cả máy đang Active ...'));
			frappe.call({
				method: "vinatex.vinatex.doctype.overrides.timekeeping.test_device_connection",
				args: { timeout: 5 },
				always: () => frappe.dom.unfreeze(),
				callback: (r) => {
					const rows = (r.message || []).map(res => `
						<tr>
							<td style="padding:4px 10px"><b>${res.name}</b></td>
							<td style="padding:4px 10px">${res.ip}:${res.port}</td>
							<td style="padding:4px 10px">${res.tcp_ok ? '<span style="color:#16a34a">TCP OK</span>' : '<span style="color:#dc2626">TCP FAIL</span>'}</td>
							<td style="padding:4px 10px">${res.zk_ok ? '<span style="color:#16a34a">ZK OK</span>' : '<span style="color:#dc2626">ZK FAIL</span>'}</td>
							<td style="padding:4px 10px">${res.log_count ?? '-'}</td>
							<td style="padding:4px 10px;color:#dc2626">${res.error ? frappe.utils.escape_html(res.error) : ''}</td>
						</tr>`).join('');
					frappe.msgprint({
						title: __('Kết quả test tất cả thiết bị'),
						message: `<table style="width:100%;border-collapse:collapse">
							<thead><tr style="background:#f5f6f7">
								<th style="padding:6px 10px;text-align:left">Thiết bị</th>
								<th style="padding:6px 10px;text-align:left">Địa chỉ</th>
								<th style="padding:6px 10px;text-align:left">TCP</th>
								<th style="padding:6px 10px;text-align:left">ZK</th>
								<th style="padding:6px 10px;text-align:left">Số log</th>
								<th style="padding:6px 10px;text-align:left">Lỗi</th>
							</tr></thead>
							<tbody>${rows}</tbody>
						</table>`
					});
				}
			});
		});
	}
});

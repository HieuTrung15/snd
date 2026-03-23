frappe.ui.form.on("VNT CVE Source", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.source_code) {
			return;
		}
		frm.add_custom_button(__("Run Sync Now"), () => {
			frappe.confirm(__("Run sync for this source now?"), () => {
				frappe.call({
					method: "vinatex.vnt_itsec.sync.run.trigger_sync",
					args: { source_code: frm.doc.source_code },
					freeze: true,
					callback: (resp) => {
						if (!resp || resp.exc) {
							return;
						}
						frappe.show_alert({
							message: __("Sync job queued for {0}", [frm.doc.source_code]),
							indicator: "green",
						});
					},
				});
			});
		});
		if (frm.doc.source_code === "NVD") {
			frm.add_custom_button(__("Run Backfill Now"), () => {
				frappe.confirm(__("Run monthly NVD backfill for this source now?"), () => {
					frappe.call({
						method: "vinatex.vnt_itsec.sync.run.trigger_sync",
						args: { source_code: frm.doc.source_code, mode: "BACKFILL" },
						freeze: true,
						callback: (resp) => {
							if (!resp || resp.exc) {
								return;
							}
							frappe.show_alert({
								message: __("Backfill job queued for {0}", [frm.doc.source_code]),
								indicator: "green",
							});
						},
					});
				});
			});
		}
	},
});

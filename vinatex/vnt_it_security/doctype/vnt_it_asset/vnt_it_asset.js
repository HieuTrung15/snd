// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

function buildCpeName(prefix, version) {
	const cleanPrefix = (prefix || "").trim();
	const cleanVersion = (version || "").trim();
	if (!cleanPrefix || !cleanVersion) {
		return "";
	}
	if (cleanPrefix.includes("{version}")) {
		return cleanPrefix.replaceAll("{version}", cleanVersion);
	}
	if (!cleanPrefix.startsWith("cpe:2.3:")) {
		return "";
	}
	if (cleanPrefix.endsWith(":")) {
		return `${cleanPrefix}${cleanVersion}`;
	}
	const parts = cleanPrefix.split(":");
	if (parts.length >= 6 && ["", "*", "-"].includes(parts[5])) {
		parts[5] = cleanVersion;
		return parts.join(":");
	}
	return `${cleanPrefix}:${cleanVersion}`;
}

function hydrateComponentFromProduct(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.product) {
		return;
	}
	frappe.db
		.get_value("VNT IT Product", row.product, ["vendor", "default_cpe_prefix"])
		.then((res) => {
			const data = (res && res.message) || {};
			if (!row.vendor && data.vendor) {
				frappe.model.set_value(cdt, cdn, "vendor", data.vendor);
			}
			if (!row.cpe_name && row.version && data.default_cpe_prefix) {
				const cpe = buildCpeName(data.default_cpe_prefix, row.version);
				if (cpe) {
					frappe.model.set_value(cdt, cdn, "cpe_name", cpe);
					return;
				}
			}
			if (!row.cpe_name && row.version) {
				frappe.call({
					method: "vinatex.vnt_it_security.doctype.vnt_it_asset.vnt_it_asset.suggest_cpe_name",
					args: {
						product: row.product,
						version: row.version,
						vendor: row.vendor || data.vendor,
						use_external: 1,
					},
					callback: (r) => {
						const message = (r && r.message) || {};
						const currentRow = locals[cdt] && locals[cdt][cdn];
						if (!currentRow || currentRow.cpe_name || !message.cpe_name) {
							return;
						}
						frappe.model.set_value(cdt, cdn, "cpe_name", message.cpe_name);
					},
				});
			}
		});
}

frappe.ui.form.on("VNT IT Asset", {
	refresh(frm) {
		if (!frm.is_new()) {
			return;
		}
		if (frm.doc.company && frm.doc.owner_department) {
			return;
		}
		frappe.db.get_value(
			"Employee",
			{ user_id: frappe.session.user },
			["company", "department"]
		).then((r) => {
			const data = r && r.message ? r.message : {};
			if (!frm.doc.company && data.company) {
				frm.set_value("company", data.company);
			}
			if (!frm.doc.owner_department && data.department) {
				frm.set_value("owner_department", data.department);
			}
		});
	},
});

frappe.ui.form.on("VNT IT Software Component", {
	product(frm, cdt, cdn) {
		hydrateComponentFromProduct(cdt, cdn);
	},
	version(frm, cdt, cdn) {
		hydrateComponentFromProduct(cdt, cdn);
	},
	cpe_name(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.cpe_name) {
			return;
		}
		const value = (row.cpe_name || "").trim();
		if (value !== row.cpe_name) {
			frappe.model.set_value(cdt, cdn, "cpe_name", value);
		}
	},
});

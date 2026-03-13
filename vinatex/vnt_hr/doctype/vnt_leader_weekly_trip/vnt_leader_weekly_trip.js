frappe.ui.form.on("VNT Leader Weekly Trip", {
	setup(frm) {
		frm.set_query("employee", "items", () => ({
			filters: {
				custom_designation_group: "Người quản lý",
			},
		}));
	},
});

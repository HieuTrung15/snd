// Employee List adapter for the shared effective-dated Shift Group workflow.

const VNTEmployeeShiftGroupList = (() => {
	function setupDesk(
		frappe,
		transferUI = globalThis.VNTShiftGroupTransferUI,
	) {
		if (!frappe || !transferUI) return;
		const translate = typeof __ === "function" ? __ : (value) => value;
		const existing = frappe.listview_settings.Employee || {};
		const originalOnload = existing.onload;

		frappe.listview_settings.Employee = Object.assign({}, existing, {
			onload(listview) {
				if (originalOnload) originalOnload(listview);
				if (!hasAnyTransferRole(frappe)) return;

				listview.page.add_actions_menu_item(
					translate("Phân / chuyển kíp hàng loạt"),
					() => {
						const employees = listview
							.get_checked_items()
							.map((row) => row.name);
						if (!employees.length) {
							frappe.msgprint(translate("Hãy chọn ít nhất một nhân sự."));
							return;
						}
						transferUI.openTransferDialog({
							frappe,
							employees,
							title: translate("Phân / chuyển kíp hàng loạt ({0} nhân sự)", [
								employees.length,
							]),
							onCompleted: () => listview.refresh(),
						});
					},
				);

				if (!frappe._vnt_shift_group_transfer_listener) {
					frappe._vnt_shift_group_transfer_listener = true;
					frappe.realtime.on(
						"vnt_bulk_shift_group_transfer_completed",
						(result) => {
							transferUI.handleRealtimeResult(frappe, translate, result);
							listview.refresh();
						},
					);
				}
			},
		});
	}

	function hasAnyTransferRole(frappe) {
		return ["HR User", "HR Manager", "System Manager"].some((role) =>
			frappe.user.has_role(role),
		);
	}

	return { setupDesk };
})();

if (typeof module !== "undefined" && module.exports) {
	module.exports = VNTEmployeeShiftGroupList;
}

if (typeof frappe !== "undefined") {
	VNTEmployeeShiftGroupList.setupDesk(frappe);
}

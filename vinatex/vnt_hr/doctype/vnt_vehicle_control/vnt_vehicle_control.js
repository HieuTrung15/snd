frappe.ui.form.on("VNT Vehicle Control", {
    date (frm) {
        loadTakenVehicle(frm)
    },
    refresh (frm) {
        if (frm.is_new()) {
            frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "employee_name")
            .then(r => {
                if (r.message && r.message.employee_name) {
                    frm.set_value("employee_name", r.message.employee_name);
                }
            });
        }
    }
});

function loadTakenVehicle(frm) {
    if (!frm.doc.date) {
		if (frm.doc.taken && frm.doc.taken.length) {
			frm.clear_table("taken");
			frm.refresh_field("taken");
			frm.doc.__unsaved = false;
		}
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_vehicle_control.vnt_vehicle_control.get_taken_vehicles",
		args: {
			date: frm.doc.date,
	    },
		callback(res) {
			frm.clear_table("taken");
			(res.message || []).forEach((item) => {
				const row = frm.add_child("taken", {
					start: item.start,
					end: item.end,
					employee_name: item.employee_name,
					date: item.date,
                    driver: item.driver,
                    id_parent: item.id_parent
				});
				row.__islocal = false;
			});
			frm.refresh_field("taken");
			frm.doc.__unsaved = false;
		},
	});
}
frappe.ui.form.on("VNT Vehicle Control", {
    date (frm) {
        loadTakenVehicle(frm)
    },
	refresh (frm) {
		loadTakenVehicle(frm)
        if (frm.is_new()) {
            frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "employee_name")
            .then(r => {
                if (r.message && r.message.employee_name) {
                    frm.set_value("employee_name", r.message.employee_name);
                }
            });
        }
    },
	onload (frm) {
		frm.set_query("driver", "items", function (doc, cdt, cdn) {
			let d = locals[cdt][cdn];
			return {
				filters: {
					status: 1
				},
			};
		});
	}
});

function loadTakenVehicle(frm) {
	const update_taken_table = (items) => {
		with_suspended_dirty(frm, () => {
			frm.clear_table("taken");
			(items || []).forEach((item) => {
				const row = frm.add_child("taken", {
					start: item.start,
					end: item.end,
					employee_name: item.employee_name,
					date: item.date,
					time: item.time,
					driver: item.driver,
					id_parent: item.id_parent
				});
				row.__islocal = false;
			});
			frm.refresh_field("taken");
		});
	};

    if (!frm.doc.date) {
		if (frm.doc.taken && frm.doc.taken.length) {
			update_taken_table([]);
		}
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_vehicle_control.vnt_vehicle_control.get_taken_vehicles",
		args: {
			date: frm.doc.date,
	    },
		callback(res) {
			update_taken_table(res.message || []);
		},
	});
}

const with_suspended_dirty = (frm, fn) => {
	const original_dirty = frm.dirty;
	frm.dirty = () => {};
	try {
		fn();
	} finally {
		frm.dirty = original_dirty;
	}
};

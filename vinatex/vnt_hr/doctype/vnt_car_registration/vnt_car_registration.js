// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Car Registration", {
    after_save(frm) {
        // Chỉ auto chạy 1 lần khi còn ở state "Mới tạo"
        if (frm.doc.workflow_state === "Mới tạo") {
            frappe.call({
                method: "frappe.model.workflow.apply_workflow",
                args: {
                    doc: frm.doc,
                    action: "Chuyển duyệt", // action trong workflow
                },
                callback() {
                    frm.reload_doc();
                }
            });
        }
	},
	refresh(frm) {
        if (frm.is_new()) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Employee",
                    filters: { user_id: frappe.session.user },
                    fieldname: ["name", "employee_name"]
                },
                callback: function (r) {
                    if (!r.message) return;
                    const exists = frm.doc.list_emp?.some(
                        e => e.employee == r.message.name
                    );
                    if (!exists) {
                        frm.add_child("list_emp", {
                            employee: r.message.name,
                            full_name: r.message.employee_name
                        });
                        frm.refresh_field("list_emp");
                        sync_list_emp_titles(frm);
                    }
                }
            });
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_employee_name",
                args: {
                    user: frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("employee", r.message);
                    }
                }
            });
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_reports_to",
                args: {
                    user: frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("approver", r.message[0]);
                        frm.set_value("approver_name", r.message[1]);
                        sync_employee_link_title(frm, "approver", "approver_name");
                    }
                }
            });
        }
        sync_list_emp_titles(frm);
	},
    employee(frm) {
        frappe.call({
            method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.check_leave_approver_2",
            args: {
                employee: frm.doc.employee
            },
            callback: function (r) {
                frm.set_value("leave_approver_2", r.message);
            }
        });
    },
    distance(frm) {
        if (frm.doc.distance) {
            // frm.set_value("approver_lv2", "tanpv@vinatex.com.vn")
            // frm.set_value("approver_name_lv2", "Phạm Văn Tân")
        }
    },
    driver(frm) {
        if (frm.doc.driver) {
            frappe.db.get_value("VNT Vehicle", {"name": frm.doc.driver}, "car_id")
            .then(r => {
                if (r && r.message && r.message.car_id) {
                    frm.set_value("car_type", r.message.car_id);
                }
            });
        }
    },
    out_of_service (frm) {
        if (frm.doc.out_of_service) {
            frm.set_value("driver", null);
            frm.set_value("car_type", null);
        }
    },
    list_emp (frm) {
        sync_list_emp_titles(frm);
    }
});


function update_emp_list_name(frm) {
	if (!frm.doc) {
		return;
	}

	let rows = frm.doc.list_emp || [];
	if (typeof rows === "string") {
		try {
			rows = JSON.parse(rows);
		} catch (e) {
			rows = [];
		}
	}
	if (!Array.isArray(rows)) {
		rows = [];
	}

	const employee_ids = rows.map((row) => row.employee).filter(Boolean);
	frm.set_value("people", employee_ids.length);

	if (!employee_ids.length) {
		frm.set_value("emp_list_name", "");
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_employee_names",
		args: { names: employee_ids },
		callback: function (r) {
			const mapping = r.message || {};
			const names = employee_ids.map((id) => mapping[id] || id);
			frm.set_value("emp_list_name", names.join(", "));
		},
	});
}

// hàm hiển thị tên employee trong tablemultiselect
function sync_list_emp_titles(frm) {
	if (!frm.doc) {
		return;
	}

	let rows = frm.doc.list_emp || [];
	if (typeof rows === "string") {
		try {
			rows = JSON.parse(rows);
		} catch (e) {
			rows = [];
		}
	}
	if (!Array.isArray(rows)) {
		rows = [];
	}

	const known = {};
	rows.forEach((row) => {
		if (row?.employee && row?.full_name) {
			known[row.employee] = row.full_name;
		}
	});
	Object.keys(known).forEach((id) => {
		frappe.utils.add_link_title("Employee", id, known[id]);
	});

	const missing = [...new Set(rows.map((row) => row?.employee).filter(Boolean))].filter(
		(id) => !known[id]
	);

	if (!missing.length) {
		frm.refresh_field("list_emp");
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_employee_names",
		args: { names: missing },
		callback: function (r) {
			const mapping = r.message || {};
			Object.keys(mapping).forEach((id) => {
				frappe.utils.add_link_title("Employee", id, mapping[id]);
			});
			frm.refresh_field("list_emp");
		},
	});
}

// hiển thị tên approver khi là readonly
function sync_employee_link_title(frm, link_field, name_field) {
	if (!frm?.doc) {
		return;
	}
	const id = frm.doc[link_field];
	if (!id) {
		return;
	}
	// const label = name_field ? frm.doc[name_field] : "";
	// if (label) {
	// 	frappe.utils.add_link_title("Employee", id, label);
	// 	frm.refresh_field(link_field);
	// 	return;
	// }
	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_employee_display_name",
		args: { employee: id },
		callback: function (r) {
			if (r.message) {
				frappe.utils.add_link_title("Employee", id, r.message);
			}
			frm.refresh_field(link_field);
		},
	});
}

// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Car Registration", {
    // after_save(frm) {
    //     // Chỉ auto chạy 1 lần khi còn ở state "Mới tạo"
    //     if (frm.doc.workflow_state === "Mới tạo") {
    //         frappe.call({
    //             method: "frappe.model.workflow.apply_workflow",
    //             args: {
    //                 doc: frm.doc,
    //                 action: "Chuyển duyệt", // action trong workflow
    //             },
    //             callback() {
    //                 frm.reload_doc();
    //             }
    //         });
    //     }
    // },
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
                            employee_name: r.message.employee_name
                        });
                        frm.refresh_field("list_emp");
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
                    }
                }
            });
        }
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
        // hiển thị tên nhân viên của trường TableMultiSelect
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

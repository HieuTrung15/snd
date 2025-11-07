// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Car Registration", {
	 refresh(frm) {
        set_title(frm)
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

                frm.add_child("list_emp", {
                    employee: r.message.name,
                    employee_name: r.message.employee_name
                });
                frm.refresh_field("list_emp");
                set_title(frm)
                
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
            frm.set_value("approver_lv2", "VGT00079")
            frm.set_value("approver_name_lv2", "Phạm Văn Tân")
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
        frm.set_value('people', frm.doc.list_emp.length)
        set_title(frm)
    }
});


function set_title(frm) {
	if (frm.doc.list_emp) {
		let data = []
		if (frm.fields_dict.list_emp.input_area.childNodes.length) {
			data = frm.fields_dict.list_emp.input_area.childNodes
		} else if (frm.fields_dict.list_emp.disp_area.childNodes.length) {
			data = frm.fields_dict.list_emp.disp_area.childNodes
		}
		$.each(data, function (i, s) {
			let value = ''
			if (s.dataset) {
				value = s.dataset.value || s.dataset.name
			}
			if (value) {
				frappe.call({
					method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_list_employee_name",
					args: {
                        "name": value
                    },
                    callback: function (r) {
                        if (r.message) {
                            s.innerHTML = s.innerHTML.replace(value, r.message)
                        }
                    }
                });
			}
		});
	}
}

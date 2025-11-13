frappe.ui.form.on('VNT Business Trip Request', {
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
            if (!frm.doc.employee) {
                frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
                .then(r => {
                    if (r && r.message && r.message.name) {
                        frm.set_value("employee", r.message.name);
                    }
                });
            }
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_reports_to",
                args: {
                    user: frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        // frm.set_value("approver", r.message[0]);
                        frm.set_value("approver_name", r.message[1]);
                    }
                }
            });
        }
	},
    vehicle(frm) {
        const targets = [
            "Ô tô TĐ (trên 40 km)",
            "Ô tô TĐ (dưới 40 km)",
            "Ô tô (TĐ chịu chi phí)",
            "Máy bay (TĐ trả chi phí)"
        ];
        const conditionTargets = [
            "Ô tô TĐ (trên 40 km)",
            "Máy bay (Đơn vị trả chi phí)",
            "Máy bay (TĐ trả chi phí)",
        ];

        // frm.doc.vehicle là CHILD TABLE, mảng object
        const vehicles = frm.doc.vehicle || [];

        // Xoá hết bảng con transportation rồi tạo lại
        frm.clear_table("transportation");

        const today = frappe.datetime.get_today();
        const now   = frappe.datetime.now_time();

        let hasVehicleCondition = false;

        vehicles.forEach(v => {
            const val = v.vehicle_type;  // lấy giá trị text thực sự

            if (!val) return;

            if (targets.includes(val)) {
                const row = frm.add_child("transportation");
                row.vehicle_item = val;  // gán đúng giá trị vào trường vehicle_item
                row.date = today;
                row.time = now;
            }

            if (!hasVehicleCondition && conditionTargets.includes(val)) {
                hasVehicleCondition = true;
            }
        });
        frm.refresh_field("transportation");
        frm.set_value("check_vehicle_condition", hasVehicleCondition ? 1 : 0);
        if (hasVehicleCondition) {
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_business_trip_request.vnt_business_trip_request.get_leave_approver_level_2",
                args: {
                    employee: frm.doc.employee,
                },
                callback (r) {
                    if (r.message) {
                        console.log("abc", r.message)
                        frm.set_value("approver_lv2", r.message.name);
                        frm.set_value("approver_name_lv2", r.message.employee_name);

                    }
                }
			});
        }
    }
});

frappe.ui.form.on('VNT Business Trip Request Items', {
    employee(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.call({
            method: "vinatex.vnt_hr.doctype.vnt_business_trip_request.vnt_business_trip_request.get_employee",
            args: {
                employee: row.employee
            },
            callback: function(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "employee_name", r.message.employee_name);
                    frappe.model.set_value(cdt, cdn, "department", r.message.department);
                    frappe.model.set_value(cdt, cdn, "designation", r.message.designation);
                    frappe.model.set_value(cdt, cdn, "salutation", r.message.salutation);
                }
            }
        })
        
    },
});


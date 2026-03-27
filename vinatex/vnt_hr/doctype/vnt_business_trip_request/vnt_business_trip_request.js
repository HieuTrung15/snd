const ensure_creator_in_items = (frm) => {
    if (!frm.doc.employee) return;
    const exists = (frm.doc.items || []).some(row => row.employee === frm.doc.employee);
    if (exists) return;

    frappe.call({
        method: "vinatex.vnt_hr.doctype.vnt_business_trip_request.vnt_business_trip_request.get_employee",
        args: {
            employee: frm.doc.employee
        },
        callback: function (r) {
            const info = r.message || {};
            const row = frm.add_child("items");
            row.employee = frm.doc.employee;
            row.employee_name = info.employee_name || frm.doc.employee_name;
            row.department = info.department || frm.doc.department;
            row.designation = info.designation || frm.doc.designation;
            row.salutation = info.salutation;
            frm.refresh_field("items");
        }
    });
};

const ensure_initial_workflow_state = (frm) => {
    if (!frm.is_new()) {
        return;
    }
    const initial_state = "Mới tạo";
    if (frm.doc.workflow_state !== initial_state) {
        frm.doc.workflow_state = initial_state;
        frm.refresh_field("workflow_state");
    }
};

const AUTO_WORKFLOW_STATE = "Mới tạo";
const AUTO_WORKFLOW_ACTION = "Chuyển duyệt";

const apply_initial_workflow_transition = (frm) => {
    if (frm.is_new() || !frm._should_apply_initial_workflow) return;
    frm._should_apply_initial_workflow = false;
    frappe.call({
        method: "frappe.model.workflow.apply_workflow",
        args: {
            doc: {
                doctype: frm.doc.doctype,
                name: frm.doc.name,
            },
            action: AUTO_WORKFLOW_ACTION,
        },
        callback() {
            frm.reload_doc();
        }
    });
};

frappe.ui.form.on('VNT Business Trip Request', {
    after_save(frm) {
        // Đánh dấu để thực thi sau khi form refresh với tên chính thức
        frm._should_apply_initial_workflow = frm.doc.workflow_state === AUTO_WORKFLOW_STATE;
    },
    before_save(frm) {
		ensure_initial_workflow_state(frm);
	},
    before_workflow_action(frm) {
		if (frm.selected_workflow_action !== "Từ chối") return;
		// Workflow mặc định freeze trước khi trigger event, cần mở ra để thao tác popup
		frappe.dom.unfreeze();

		return new Promise((resolve, reject) => {
			let confirmed = false;
			const dialog = new frappe.ui.Dialog({
				title: __("Lý do từ chối"),
				fields: [
					{
						fieldname: "reject_reason",
						fieldtype: "Small Text",
						label: __("Lý do"),
						reqd: 1,
						default: frm.doc.custom_reject_reason || "",
					},
				],
				primary_action_label: __("Từ chối"),
				primary_action(values) {
					const reject_reason = (values.reject_reason || "").trim();
					if (!reject_reason) {
						frappe.msgprint(__("Vui lòng nhập lý do từ chối."));
						return;
					}
					// Freeze lại để tránh bấm lặp trong lúc ghi dữ liệu
					frappe.dom.freeze();
					frappe.db
						.set_value(frm.doctype, frm.doc.name, "reject_reason", reject_reason)
						.then(() => {
							confirmed = true;
							frm.set_value("reject_reason", reject_reason);
							dialog.hide();
							resolve();
						})
						.catch(() => {
							frappe.dom.unfreeze();
							frappe.msgprint(__("Không thể lưu lý do từ chối. Vui lòng thử lại."));
						});
					},
				secondary_action_label: __("Quay lại"),
				secondary_action() {
					dialog.hide();
				},
			});

			dialog.onhide = () => {
				if (confirmed) return;
				frm.selected_workflow_action = null;
				reject();
			};

			dialog.show();
		});
	},
	refresh(frm) {
        if (frm._should_apply_initial_workflow && !frm.is_new()) {
            apply_initial_workflow_transition(frm);
        }
	    if (frm.is_new()) {
            ensure_initial_workflow_state(frm);
            if (!frm.doc.employee) {
                frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
                .then(r => {
                    if (r && r.message && r.message.name) {
                        frm.set_value("employee", r.message.name);
                    }
                });
            }
            ensure_creator_in_items(frm);
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
    employee(frm) {
        if (frm.is_new()) {
            ensure_creator_in_items(frm);
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

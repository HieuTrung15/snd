frappe.ui.form.on('VNT Business Trip Request', {
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
        if (!frm.doc.employee) {
            frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
            .then(r => {
                if (r && r.message && r.message.name) {
                    frm.set_value("employee", r.message.name);
                }
            });
        }
	},
    vehicle(frm) {
        const targets = [
            "Ô tô TĐ (trên 40 km)",
            "Ô tô TĐ (dưới 40 km)",
            "Ô tô (TĐ chịu chi phí)",
            // "Máy bay (TĐ trả chi phí)"
        ];

        // frm.doc.vehicle là CHILD TABLE, mảng object
        const vehicles = frm.doc.vehicle || [];

        // Xoá hết bảng con transportation rồi tạo lại
        frm.clear_table("transportation");

        const today = frappe.datetime.get_today();
        const now   = frappe.datetime.now_time();

        vehicles.forEach(v => {
            const val = v.vehicle_type;  // lấy giá trị text thực sự

            if (!val || !targets.includes(val)) return;  // chỉ xử lý nếu nằm trong targets

            const row = frm.add_child("transportation");
            row.vehicle_item = val;  // gán đúng giá trị vào trường vehicle_item
            row.date = today;
            row.time = now;
        });

        frm.refresh_field("transportation");
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



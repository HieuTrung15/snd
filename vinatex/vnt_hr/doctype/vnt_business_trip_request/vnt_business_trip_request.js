frappe.ui.form.on('VNT Business Trip Request', {
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
        // lấy danh sách được chọn
        let selected = frm.doc.vehicle || [];

        // nếu là MultiSelectList, sẽ là array
        // nếu là MultiSelect thường (string), convert:
        if (typeof selected === 'string') {
            selected = selected.split('\n').filter(v => v && v.trim());
        }

        // Xoá bảng cũ (tuỳ bạn, hoặc merge thì sửa lại)
        frm.clear_table('transportation');

        const today = frappe.datetime.get_today();
        const now = frappe.datetime.now_time();

        selected.forEach(v => {
            const row = frm.add_child('transportation');
            row.date = today;
            row.time = now;
        });

        frm.refresh_field('transportation');
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



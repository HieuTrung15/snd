// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Decision", {
	refresh(frm) {
        if (!frm.doc.employee) {
            frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
            .then(r => {
                if (r && r.message && r.message.name) {
                    frm.set_value("employee", r.message.name);
                }
            });
        }
        // tự động lấy date là ngày tạo phiếu
        if (!frm.doc.date) {
            frm.set_value("date", frappe.datetime.get_today());
        }
	},
    button(frm) {
        if (!frm.doc.department_re) {
            frappe.msgprint(__("Hãy chọn Phòng/Ban cần lấy danh sách nhân sự trước."));
            return;
        }
        frappe.call ({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Employee',
                fields: ['name', 'employee_name', 'department', 'designation'],
                filters: {
                    status: 'Active',
                    department: frm.doc.department_re
                },
                limit_page_length: 0,
            },
            freeze: true,
            freeze_message: __('Đang lấy danh sách nhân sự...'),
        }).then(r => {
        const rows = r.message || [];
        rows.forEach(row => {
            const d = frm.add_child('items');
            d.employee = row.name;             
            d.cur_department = row.department;  
            d.cur_designation = row.designation;
        });

        frm.refresh_field('items');
        frappe.show_alert({ message: __('Đã lấy {0} nhân sự', [rows.length]), indicator: 'green' });
        });
    },
});

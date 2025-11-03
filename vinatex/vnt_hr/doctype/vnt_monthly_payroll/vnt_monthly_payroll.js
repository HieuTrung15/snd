// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Monthly Payroll", {
	refresh(frm) {

	},
    compute_row(frm, row) {
        if (!row || !row.employee) return;

        const args = {
            employee: row.employee,
            company: frm.doc.company,
            month: frm.doc.month,
            year: frm.doc.year
        };

        frappe.call({
        method:
            "vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll.compute_item",
        args,
        freeze: true,
        // freeze_message: __("Đang tính lương cho {0}", [row.employee]),
        }).then((r) => {
        if (!r || !r.message) return;
            // Lương cơ bản (7)
            frappe.model.set_value(row.doctype, row.name, "luong_cb", r.message.regional_minimum_wage*row.hs_luong_cb);
            // PC Đảng 1 (9)
            frappe.model.set_value(row.doctype, row.name, "pc_dang1", r.message.regional_minimum_wage*row.hs_pc_dang_1);
            // PC kiêm nhiệm 1 (11)
            frappe.model.set_value(row.doctype, row.name, "pc_kiem_nhiem1", r.message.regional_minimum_wage*row.hs_pc_kiem_nhiem1);

            //Tổng lương cơ bản và phụ cấp (12)
            if (row.bhxh == '')
                //nếu không tham gia bhxh thì tổng lương cơ bản = 0
                frappe.model.set_value(row.doctype, row.name, "tong_luong_cb", 0);
            else
                //nếu tổng cơ cb + pc đảng + pc kiêm nhiệm > 20 lần lương tham chiếu thì lấy bằng 20 lần lương tham chiếu
                if ((row.luong_cb + row.pc_dang1 + row.pc_kiem_nhiem1)>20*r.message.reference_salary)
                    frappe.model.set_value(row.doctype, row.name, "tong_luong_cb", 20*r.message.reference_salary);
                // ngược lại lấy bằng tổng lương cb + pc đảng + pc kiêm nhiệm
                else
                    frappe.model.set_value(row.doctype, row.name, "tong_luong_cb", row.luong_cb + row.pc_dang1 + row.pc_kiem_nhiem1);

            // số ngày phép (13) lấy từ Attendance
           //frappe.model.set_value(row.doctype, row.name, "sophep", r.message.travel_allowance);

           frm.refresh_field("items");
        });
    }
});

frappe.ui.form.on("VNT Monthly Payroll Item", {
    employee(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        frm.events.compute_row(frm, row);
    },
});


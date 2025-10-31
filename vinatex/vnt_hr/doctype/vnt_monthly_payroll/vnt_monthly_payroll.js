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
            payroll_month: frm.doc.month,
            payyroll_year: frm.doc.year
        };

        frappe.call({
        method:
            "vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll.compute_item",
        args,
        freeze: true,
        freeze_message: __("Đang tính lương cho {0}", [row.employee]),
        }).then((r) => {
        if (!r || !r.message) return;
    
        frappe.model.set_value(row.doctype, row.name, r.message);
        frm.refresh_field("items");
      
        if (frm.events.compute_totals) frm.events.compute_totals(frm);
        });
    }
});

frappe.ui.form.on("VNT Monthly Payroll Item", {
    employee(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        frm.events.compute_row(frm, row);
    },
});


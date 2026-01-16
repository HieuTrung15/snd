// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT KPI Nam", {
	refresh(frm) {
        // nếu trường employee trống thì sẽ tìm đến employee của user hiện tại đang tạo phiếu
        if(!frm.doc.employee) {
            frappe.db.get_value("Employee", {user_id: frappe.session.user}, "name")
            .then(r => {
                if(r.message) {
                    frm.set_value("employee", r.message.name);
                }
            })
        };     
        //nếu trường date trống thì sẽ tự động điền ngày hiện tại
        if(!frm.doc.date) {
            frm.set_value("date", frappe.datetime.get_today());
        }
        //nếu trường kpi_year trống thì tự động điền năm hiện tại
        if(!frm.doc.kpi_year) {
            frm.set_value("kpi_year", frappe.datetime.get_today().substr(0,4));
        }
	},
});

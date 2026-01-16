// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

const load_kpi_ban_items = (frm) => {
    const kpiYear = frm.doc.kpi_year;
    const department = frm.doc.department;

    if (!kpiYear || !department) {
        return;
    }

    const filters = {
        kpi_year: kpiYear,
        department: department,
    };

    if (frm.doc.type) {
        filters.type = frm.doc.type;
    }

    const fetch_items = () => {
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "VNT KPI Ban",
                fields: ["name"],
                filters: filters,
                order_by: "modified desc",
                limit_page_length: 1,
            },
            freeze: true,
            freeze_message: __("Loading KPI Ban..."),
        }).then((r) => {
            const rows = r.message || [];
            if (!rows.length) {
                frappe.msgprint(
                    __(
                        "Không tìm thấy công việc nào năm {0} cho Ban {1}.",
                        [kpiYear, department]
                    )
                );
                return;
            }

            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "VNT KPI Ban",
                    name: rows[0].name,
                },
            }).then((docRes) => {
                const source = docRes.message || {};
                const items = source.items || [];

                frm.clear_table("items");
                items.forEach((item) => {
                    const row = frm.add_child("items");
                    row.kpi_details = item.kpi_details;
                });

                frm.refresh_field("items");
            });
        });
    };

    if (frm.doc.items && frm.doc.items.length) {
        frappe.confirm(
            __("Bạn có muốn lấy dữ liệu KPI của Phòng/Ban tự động?"),
            () => {
                fetch_items();
            },
            () => {}
        );
    } else {
        fetch_items();
    }
};

frappe.ui.form.on("VNT KPI Chuyen Vien", {
    kpi_year(frm) {
        load_kpi_ban_items(frm);
    },
    department(frm) {
        load_kpi_ban_items(frm);
    },
   
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

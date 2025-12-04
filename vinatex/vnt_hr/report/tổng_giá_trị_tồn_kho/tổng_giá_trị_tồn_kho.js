frappe.query_reports["Tổng giá trị tồn kho"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 0,
            default: frappe.defaults.get_user_default("Company")
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
            reqd: 0,
            get_query: function() {
                const company = frappe.query_report.get_filter_value("company");
                // Nếu có chọn company thì lọc kho theo company
                if (company) {
                    return {
                        filters: {
                            company: company
                        }
                    };
                }
                // Không chọn company thì trả tất cả kho
                return {};
            }
        }
    ]
};

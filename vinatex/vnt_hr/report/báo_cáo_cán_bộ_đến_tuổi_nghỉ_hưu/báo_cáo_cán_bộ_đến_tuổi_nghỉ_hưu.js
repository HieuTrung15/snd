// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Báo cáo cán bộ đến tuổi nghỉ hưu"] = {
	"filters": [
        {
            fieldname: "as_of_date",
            label: "Ngày chốt",
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today()
        },
        {
            fieldname: "months_ahead",
            label: "Trong vòng (tháng)",
            fieldtype: "Int",
            reqd: 1,
            default: 6
        },
        {
            fieldname: "include_overdue",
            label: "Đã nghỉ hưu",
            fieldtype: "Check",
            default: 0
        },
        {
            fieldname: "company",
            label: "Công ty",
            fieldtype: "Link",
            options: "Company"
        },
        {
            fieldname: "department",
            label: "Phòng ban",
            fieldtype: "Link",
            options: "Department"
        },
        {
            fieldname: "gender",
            label: "Giới tính",
            fieldtype: "Select",
            options: ["Tất cả", "Nam", "Nữ", "Male", "Female"].join("\n"),
            default: "Tất cả"
        },
        {
            fieldname: "age_male",
            label: "Tuổi nghỉ hưu (Nam)",
            fieldtype: "Int",
            default: 62
        },
        {
            fieldname: "age_female",
            label: "Tuổi nghỉ hưu (Nữ)",
            fieldtype: "Int",
            default: 60
        }
    ],

    onload: function (report) {
        // đảm bảo as_of_date luôn có mặc định
        if (!report.get_values().as_of_date) {
            report.set_filter_value("as_of_date", frappe.datetime.get_today());
        }
    },

    // formatter để highlight gần đến hạn
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "days_until" && data) {
            const n = cint(data.days_until);
            if (n <= 0) {
                value = `<span style="color:#d32f2f;font-weight:600">${value}</span>`;
            } else if (n <= 90) {
                value = `<span style="color:#f57c00;font-weight:600">${value}</span>`;
            }
        }
        return value;
    }
};

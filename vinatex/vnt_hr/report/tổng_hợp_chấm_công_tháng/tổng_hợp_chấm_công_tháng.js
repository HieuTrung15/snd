// frappe.query_reports["Tổng hợp chấm công tháng"] = {
// 	filters: [
// 		{
// 			fieldname: "month",
// 			label: "Tháng",
// 			fieldtype: "Select",
// 			options: ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"],
// 			reqd: 1,
// 		},
// 		{
// 			fieldname: "year",
// 			label: "Năm",
// 			fieldtype: "Int",
// 			default: new Date().getFullYear(),
// 			reqd: 1,
// 		},
// 		{
//             "fieldname": "company",
//             "label": "Công ty",
//             "fieldtype": "Link",
//             "options": "Company"
//         },
// 	],
// 	onload: function (report) {
// 		// Ép user phải chọn tháng/năm (tránh kéo cả năm)
// 		const req = ["month", "year"];
// 		req.forEach((fn) => {
// 			const f = report.get_filter(fn);
// 			if (f) f.df.reqd = true;
// 		});

// 		// Nút tải nhanh
// 		report.page.add_inner_button("Xuất Excel tuỳ biến", () => {
// 		const filters = report.get_values(); // lấy filter hiện tại
// 		// Gọi server — build_xlsx_response sẽ tự trigger tải file về
// 		frappe.call({
// 			method: "vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.tổng_hợp_chấm_công_tháng.download_xlsx",
// 			args: { filters },
// 			freeze: true
// 			});
// 		});
// 	},

// 	// Tô màu nhẹ cho ô ngày theo mã
// 	formatter: function (value, row, column, data, default_formatter) {
// 		value = default_formatter(value, row, column, data);

// 		// chỉ format các cột ngày 1..31
// 		const day = parseInt(column.fieldname, 10);
// 		if (!isNaN(day) && day >= 1 && day <= 31) {
// 			const v = (data && (data[column.fieldname] || "")).toString().toUpperCase();
// 			let bg = "";
// 			if (v === "A") bg = "rgba(255, 76, 76, .15)"; // Absent: đỏ nhạt
// 			else if (v === "P") bg = "rgba(76, 175, 80, .12)"; // Present: xanh nhạt
// 			else if (v === "L") bg = "rgba(33, 150, 243, .12)"; // Leave: xanh dương nhạt
// 			else if (v === "HD") bg = "rgba(255, 193, 7, .18)"; // Half Day: vàng nhạt
// 			else if (v === "LM") bg = "rgba(156, 39, 176, .12)"; // Late: tím nhạt
// 			else if (v === "WO" || v === "H") bg = "rgba(158, 158, 158, .12)"; // Off/Holiday
// 			else if (v === "UL" || v === "") bg = "rgba(96, 125, 139, .08)"; // Unmarked

// 			if (bg) {
// 				return `<span style="background:${bg}; padding:2px 6px; border-radius:4px; display:inline-block;">${value}</span>`;
// 			}
// 		}

// 		return value;
// 	},
// };




// // tong_hop_cham_cong_thang.js
// frappe.query_reports["Tổng hợp chấm công tháng"] = {
//   "filters": [
//     {
//       "fieldname": "company",
//       "label": "Công ty",
//       "fieldtype": "Link",
//       "options": "Company",
//       "reqd": 1
//     },
//     {
//       "fieldname": "department",
//       "label": "Phòng ban",
//       "fieldtype": "Link",
//       "options": "Department"
//     },
//     {
//       "fieldname": "employee",
//       "label": "Nhân viên",
//       "fieldtype": "Link",
//       "options": "Employee"
//     },
//     {
//       "fieldname": "month",
//       "label": "Tháng",
//       "fieldtype": "Select",
//       "options": "\n01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
//       "reqd": 1
//     },
//     {
//       "fieldname": "year",
//       "label": "Năm",
//       "fieldtype": "Int",
//       "reqd": 1
//     },
//   ],
//   onload: function (report) {
//     // Lấy ngày hiện tại
//     const today = new Date();
//     const yyyy = today.getFullYear();
//     const mm = String(today.getMonth() + 1).padStart(2, "0"); // "01".."12"

//     // Set mặc định Năm/Tháng nếu chưa có
//     if (!report.get_values().year) {
//       report.set_filter_value("year", yyyy);
//     }
//     if (!report.get_values().month) {
//       report.set_filter_value("month", mm);
//     }

//     // Set mặc định Công ty theo Default Company của user/system
//     const default_company =
//       frappe.defaults.get_user_default("Company") ||
//       frappe.defaults.get_global_default("company");

//     if (default_company && !report.get_values().company) {
//       report.set_filter_value("company", default_company);
//     }
//   },
// };


frappe.query_reports["Tổng hợp chấm công tháng"] = {
  "filters": [
    {
      "fieldname": "company",
      "label": "Công ty",
      "fieldtype": "Link",
      "options": "Company",
      "reqd": 1
    },
    {
      "fieldname": "department",
      "label": "Phòng ban",
      "fieldtype": "Link",
      "options": "Department"
    },
    {
      "fieldname": "employee",
      "label": "Nhân viên",
      "fieldtype": "Link",
      "options": "Employee"
    },
    {
      "fieldname": "month",
      "label": "Tháng",
      "fieldtype": "Select",
      "options": "\n01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
      "reqd": 1,
      on_change: function () {
        const r = frappe.query_report;
        const vals = r.get_values();
        const y = parseInt(vals.year, 10);
        const m = parseInt(vals.month, 10);
        if (!isNaN(y) && !isNaN(m)) {
          const first = new Date(y, m - 1, 1);
          const last = new Date(y, m, 0);
          r.set_filter_value("from_date", frappe.datetime.obj_to_str(first));
          r.set_filter_value("to_date", frappe.datetime.obj_to_str(last));
          r.refresh();
        }
      }
    },
    {
      "fieldname": "year",
      "label": "Năm",
      "fieldtype": "Int",
      "reqd": 1,
      on_change: function () {
        const r = frappe.query_report;
        const vals = r.get_values();
        const y = parseInt(vals.year, 10);
        const m = parseInt(vals.month, 10);
        if (!isNaN(y) && !isNaN(m)) {
          const first = new Date(y, m - 1, 1);
          const last = new Date(y, m, 0);
          r.set_filter_value("from_date", frappe.datetime.obj_to_str(first));
          r.set_filter_value("to_date", frappe.datetime.obj_to_str(last));
          r.refresh();
        }
      }
    },
    {
      "fieldname": "from_date",
      "label": "Từ ngày",
      "fieldtype": "Date",
      "reqd": 1,
      "hidden": 1
    },
    {
      "fieldname": "to_date",
      "label": "Đến ngày",
      "fieldtype": "Date",
      "reqd": 1,
      "hidden": 1
    },
  ],

  onload: function (report) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0"); // "01".."12"

    // Set mặc định tháng/năm
    if (!report.get_values().year) {
      report.set_filter_value("year", yyyy);
    }
    if (!report.get_values().month) {
      report.set_filter_value("month", mm);
    }

    // Tính ngày đầu & cuối tháng theo tháng/năm đã chọn
    const vals = report.get_values();
    const y = parseInt(vals.year || yyyy, 10);
    const m = parseInt(vals.month || mm, 10);
    if (!isNaN(y) && !isNaN(m)) {
      const first = new Date(y, m - 1, 1);
      const last = new Date(y, m, 0);
      if (!vals.from_date) {
        report.set_filter_value("from_date", frappe.datetime.obj_to_str(first));
      }
      if (!vals.to_date) {
        report.set_filter_value("to_date", frappe.datetime.obj_to_str(last));
      }
    }

    // Set mặc định Công ty
    const default_company =
      frappe.defaults.get_user_default("Company") ||
      frappe.defaults.get_global_default("company");

    if (default_company && !report.get_values().company) {
      report.set_filter_value("company", default_company);
    }
  },
};


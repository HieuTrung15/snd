// Số nhân sự đi công tác — auto tuần này + auto run + không lỗi date

frappe.query_reports["Số nhân sự đi công tác"] = {
  filters: [
    { fieldname: "from_date",  label: "Từ ngày",   fieldtype: "Date" },
    { fieldname: "to_date",    label: "Đến ngày",  fieldtype: "Date" },
    { fieldname: "type_leave", label: "Loại nghỉ", fieldtype: "Data", default: "Công tác" },
    { fieldname: "department", label: "Phòng ban", fieldtype: "Link", options: "Department" }
  ],

  onload(report) {
    // luôn reset về tuần hiện tại mỗi lần mở
    const wsObj = frappe.datetime.str_to_obj(frappe.datetime.week_start());
    const weObj = frappe.datetime.str_to_obj(frappe.datetime.week_end());
    report.set_filter_value({ from_date: wsObj, to_date: weObj });

    // tự chạy ngay, không cần bấm Run
    // chặn chạy lặp bằng cờ __auto_ran
    if (!report.__auto_ran) {
      report.__auto_ran = true;
      setTimeout(() => report.refresh(), 0);
    }

    // (tuỳ chọn) auto-run khi user đổi bất kỳ filter nào
    ["from_date","to_date","type_leave","department"].forEach((f) => {
      const ctl = report.get_filter(f);
      if (ctl && !ctl.__hooked) {
        ctl.__hooked = true;
        // onchange của control → refresh
        ctl.df.onchange = () => report.refresh();
      }
    });
  }
};

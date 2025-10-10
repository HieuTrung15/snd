// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["BÁO CÁO LAO ĐỘNG BÌNH QUÂN"] = {
	filters: [
    { fieldname: "from_month", label: "From Month", fieldtype: "Data", reqd: 1 },
    { fieldname: "to_month",   label: "To Month",   fieldtype: "Data", reqd: 1 },
    { fieldname: "company",    label: "Company",    fieldtype: "Link", options: "Company" }
  ],

  onload(report) {
    // 1) Auto-refresh khi đổi filter
    report.trigger_refresh_on_change = true;

    // 2) Giá trị mặc định (đầu năm → tháng hiện tại)
    const today = frappe.datetime.now_date(); // YYYY-MM-DD
    const yyyy  = today.slice(0, 4);
    const mm    = today.slice(5, 7);
    const defaults = {
      from_month: `01/${yyyy}`,
      to_month:   `${mm}/${yyyy}`,
      company: frappe.defaults.get_user_default("Company") || undefined,
    };

    // 3) Chuẩn hoá nhập tháng về MM/YYYY
    const normalize = (v) => {
      if (!v) return v;
      v = String(v).trim();
      const ymd = v.match(/^(\d{4})-(\d{2})$/);   // YYYY-MM
      if (ymd) return `${ymd[2]}/${ymd[1]}`;
      const mmy = v.match(/^(\d{2})\/(\d{4})$/);  // MM/YYYY
      if (mmy) return v;
      return v; // backend sẽ validate
    };

    // 4) Đặt giá trị filter bằng API (bắt buộc với v15 để hệ thống “nhận”)
    const setDefaultsOnce = () => {
      report.set_filter_values({
        from_month: normalize(report.get_filter_value("from_month") || defaults.from_month),
        to_month:   normalize(report.get_filter_value("to_month")   || defaults.to_month),
        company:    report.get_filter_value("company") || defaults.company,
      });
    };

    // 5) Gắn sự kiện blur/change để tự refresh & tự chuẩn hoá
    const hook = (fname) => {
      const f = report.page.form.fields_dict[fname];
      if (!f || !f.$input) return;
      f.$input.on("blur change", () => {
        if (fname === "from_month" || fname === "to_month") {
          const val = normalize(f.$input.val());
          if (val !== undefined) f.$input.val(val);
        }
        report.refresh();
      });
    };

    // Chờ UI dựng xong rồi set default + chạy ngay
    frappe.after_ajax(() => {
      setDefaultsOnce();
      ["from_month", "to_month", "company"].forEach(hook);
      // 🔥 mở report là chạy ngay, không cần bấm
      setTimeout(() => report.refresh(), 0);
    });
  },
};
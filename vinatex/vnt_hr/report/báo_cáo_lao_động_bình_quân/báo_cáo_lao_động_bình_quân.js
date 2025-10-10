// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["BÁO CÁO LAO ĐỘNG BÌNH QUÂN"] = {
  filters: [
    { fieldname: "from_month", label: "From Month", fieldtype: "Data", reqd: 1 },
    { fieldname: "to_month",   label: "To Month",   fieldtype: "Data", reqd: 1 },
    { fieldname: "company",    label: "Company",    fieldtype: "Link", options: "Company" }
  ],

  onload(report) {
    // 1) Chỉ dùng 1 cơ chế refresh + debounce để tránh double-call
    report.trigger_refresh_on_change = false;
    const refreshDebounced = frappe.utils.debounce(() => report.refresh(), 250);

    // 2) Default: đầu năm → tháng hiện tại
    const today = frappe.datetime.get_today(); // YYYY-MM-DD
    const yyyy  = today.slice(0, 4);
    const mm    = today.slice(5, 7);
    const defaults = {
      from_month: `01/${yyyy}`,
      to_month:   `${mm}/${yyyy}`,
      company: frappe.defaults.get_user_default("Company") || undefined,
    };

    // 3) Chuẩn hoá về MM/YYYY (nhận cả YYYY-MM, YYYY/MM, M/YYYY, MM/YYYY)
    const normalize = (v) => {
      if (!v) return v;
      v = String(v).trim();
      // YYYY-MM or YYYY/MM
      let m = v.match(/^(\d{4})[-/](\d{1,2})$/);
      if (m) return `${m[2].padStart(2, "0")}/${m[1]}`;
      // MM/YYYY or M/YYYY
      m = v.match(/^(\d{1,2})\/(\d{4})$/);
      if (m) return `${m[1].padStart(2, "0")}/${m[2]}`;
      return v; // để backend validate nếu sai
    };

    // 4) Set default nếu trống (không kích hoạt onchange)
    const setIfEmpty = (fname, val) => {
      const cur = report.get_filter_value(fname);
      if (!cur) report.set_filter_value(fname, val);
    };

    // 5) Gắn onchange “đúng chỗ” trên control (không dùng blur/change trên $input)
    const hookOnChange = (fname, fn) => {
      const ctl = report.get_filter(fname);
      if (!ctl || ctl.__vnt_hooked) return;
      ctl.df.onchange = fn;
      ctl.__vnt_hooked = true; // tránh gắn lặp
    };

    frappe.after_ajax(() => {
      // Set default một lần
      setIfEmpty("from_month", normalize(defaults.from_month));
      setIfEmpty("to_month",   normalize(defaults.to_month));
      setIfEmpty("company",    defaults.company);

      // Chuẩn hoá + refresh có debounce khi đổi tháng
      hookOnChange("from_month", () => {
        const ctl = report.get_filter("from_month");
        const nv = normalize(ctl.get_value());
        if (nv !== undefined) ctl.set_input(nv);
        refreshDebounced();
      });

      hookOnChange("to_month", () => {
        const ctl = report.get_filter("to_month");
        const nv = normalize(ctl.get_value());
        if (nv !== undefined) ctl.set_input(nv);
        refreshDebounced();
      });

      // Company đổi thì refresh (debounce) — không cần normalize
      hookOnChange("company", () => refreshDebounced());

      // 🔥 Mở report chạy ngay (chỉ 1 call)
      report.refresh();
    });
  },
};

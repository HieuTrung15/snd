frappe.listview_settings['VNT Attendance Confirm'] = {
  onload(listview) {
    _setup_month_year_range_filter(listview);

    // Chỉ set filter tự động lần đầu khi load list
    if (listview.__dept_filter_applied) return;
    listview.__dept_filter_applied = true;

    // Lấy department từ Employee của user đang đăng nhập
    frappe.db.get_value(
      "Employee",
      { user_id: frappe.session.user },
      "department"
    ).then(r => {
      const dept = r?.message?.department;
      if (!dept) return;

      // Nếu user đã tự chọn department rồi thì tôn trọng, không override
      const existing = (listview.filter_area?.filters || [])
        .some(f => f[1] === "department");

      if (existing) return;

      // Add filter mặc định
      listview.filter_area.add([
        ["VNT Attendance Confirm", "department", "=", dept]
      ]);

      // Refresh list theo filter mới
      listview.refresh();
    });
  }
};

function _setup_month_year_range_filter(listview) {
  if (listview.__month_year_range_setup) return;
  listview.__month_year_range_setup = true;

  const original_get_filters_for_args = listview.get_filters_for_args.bind(listview);

  listview.get_filters_for_args = function () {
    const raw_filters = original_get_filters_for_args();
    const { month, year } = _extract_month_year(raw_filters, listview);

    const filters = raw_filters.filter((f) => f[1] !== "month" && f[1] !== "year");
    const range = _compute_month_year_range(month, year);
    if (!range) return filters;

    _push_unique_filter(filters, listview.doctype, "from_date", "<=", range.end);
    _push_unique_filter(filters, listview.doctype, "to_date", ">=", range.start);
    return filters;
  };
}

function _extract_month_year(filters, listview) {
  let month = null;
  let year = null;

  (filters || []).forEach((f) => {
    if (f[1] === "month") month = f[3];
    if (f[1] === "year") year = f[3];
  });

  const fields_dict = listview?.page?.fields_dict;
  if (fields_dict) {
    if (!month && fields_dict.month) month = fields_dict.month.get_value();
    if (!year && fields_dict.year) year = fields_dict.year.get_value();
  }

  return { month, year };
}

function _compute_month_year_range(month, year) {
  const m = parseInt(month, 10);
  const y = parseInt(year, 10);
  const has_month = Number.isFinite(m);
  const has_year = Number.isFinite(y);

  let start = null;
  let end = null;

  if (has_month && has_year) {
    if (m < 1 || m > 12) return null;
    start = new Date(y, m - 1, 1);
    end = new Date(y, m, 0);
  } else if (has_year) {
    start = new Date(y, 0, 1);
    end = new Date(y, 12, 0);
  } else if (has_month) {
    if (m < 1 || m > 12) return null;
    const current_year = new Date().getFullYear();
    start = new Date(current_year, m - 1, 1);
    end = new Date(current_year, m, 0);
  } else {
    return null;
  }

  return {
    start: frappe.datetime.obj_to_str(start),
    end: frappe.datetime.obj_to_str(end),
  };
}

function _push_unique_filter(filters, doctype, fieldname, condition, value) {
  const exists = (filters || []).some((f) =>
    f[0] === doctype &&
    f[1] === fieldname &&
    f[2] === condition &&
    f[3] === value
  );
  if (!exists) {
    filters.push([doctype, fieldname, condition, value]);
  }
}

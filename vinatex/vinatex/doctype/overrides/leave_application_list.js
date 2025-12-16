frappe.listview_settings['Leave Application'] = {
  onload(listview) {
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
        ["Leave Application", "department", "=", dept]
      ]);

      // Refresh list theo filter mới
      listview.refresh();
    });
  }
};

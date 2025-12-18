// ẩn tab Conneections cho tất cả các form, chỉ hiển thị cho System Manager
frappe.ui.form.on('*', {
    refresh(frm) {
        if (!frappe.user.has_role('System Manager')) {
            if (frm.dashboard) {
                frm.dashboard.clear_headline();
                frm.dashboard.wrapper?.hide();
            }
        }
    }
});

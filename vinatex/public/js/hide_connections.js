// ẩn tab Conneections cho tất cả các form, chỉ hiển thị cho System Manager
// frappe.ui.form.on('*', {
//     refresh(frm) {
//         if (!frappe.user.has_role('System Manager')) {
//             if (frm.dashboard) {
//                 frm.dashboard.clear_headline();
//                 frm.dashboard.wrapper?.hide();
//             }
//         }
//     }
// });

(function () {

    function hide_connections_if_needed() {
        if (!frappe.user || frappe.user.has_role("System Manager")) {
            return;
        }

        const selector = ".form-dashboard-section.form-links";

        document.querySelectorAll(selector).forEach(el => {
            el.style.display = "none";
        });
    }

    // 1. Khi trang load
    frappe.after_ajax(hide_connections_if_needed);

    // 2. Khi đổi form / đổi route
    $(document).on("page-change", hide_connections_if_needed);

    // 3. Khi DOM thay đổi (ERPNext render lại dashboard)
    const observer = new MutationObserver(hide_connections_if_needed);
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

})();


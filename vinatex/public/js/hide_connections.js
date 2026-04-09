// ẩn connections trừ System Manager
(function () {
    const WAIT_TIMEOUT_MS = 10000;
    const WAIT_STEP_MS = 100;
    const waitStartAt = Date.now();

    function hide_connections_if_needed() {
        const frappeObj = window.frappe;
        if (!frappeObj?.user || frappeObj.user.has_role("System Manager")) {
            return;
        }

        const selector = ".form-dashboard-section.form-links";

        document.querySelectorAll(selector).forEach(el => {
            el.style.display = "none";
        });
    }

    function bind() {
        if (window.frappe?.after_ajax) {
            // 1. Khi trang load
            window.frappe.after_ajax(hide_connections_if_needed);
        } else {
            setTimeout(hide_connections_if_needed, 0);
        }

        // 2. Khi đổi form / đổi route
        if (window.$) {
            $(document).on("page-change", hide_connections_if_needed);
        }
        if (window.frappe?.router?.on) {
            window.frappe.router.on("change", () => setTimeout(hide_connections_if_needed, 0));
        } else {
            window.addEventListener("hashchange", () => setTimeout(hide_connections_if_needed, 0));
        }

        // 3. Khi DOM thay đổi (ERPNext render lại dashboard)
        const observer = new MutationObserver(hide_connections_if_needed);
        if (document.body) {
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        } else {
            document.addEventListener("DOMContentLoaded", function startObserver() {
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
            }, { once: true });
        }
    }

    function waitAndBind() {
        if (window.frappe) {
            bind();
            return;
        }

        if (Date.now() - waitStartAt >= WAIT_TIMEOUT_MS) {
            return;
        }

        setTimeout(waitAndBind, WAIT_STEP_MS);
    }

    waitAndBind();
})();

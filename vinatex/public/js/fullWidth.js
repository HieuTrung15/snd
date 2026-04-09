(function () {
    function applyFullWidth() {
        if (document.body) {
            document.body.classList.add("full-width");
        }
    }

    document.addEventListener("DOMContentLoaded", applyFullWidth);

    if (window.frappe?.router?.on) {
        window.frappe.router.on("change", () => setTimeout(applyFullWidth, 0));
    } else {
        window.addEventListener("hashchange", () => setTimeout(applyFullWidth, 0));
    }
})();

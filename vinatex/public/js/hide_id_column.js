(() => {
    const WAIT_TIMEOUT_MS = 10000;
    const WAIT_STEP_MS = 100;
    const waitStartAt = Date.now();

    // Danh sách các Doctype cần ẩn cột ID
    const TARGET_DOCTYPES = [
        // 1. Hồ sơ của tôi
        "Employee", 
        // 4. Xác nhận chấm công
        "VNT Attendance Confirm",
        // 5. Thu nhập cá nhân
        "VNT Salary Slip",
        "Leave Application",
        "VNT Car Registration",
        "VNT Business Trip Request",
        "VNT Meeting Room Booking",
        "VNT External Products",
        "VNT Courier Registration",
        "VNT Payment Request",
        // thêm ở đây...
        // trong view setting của doctype, thay Title Field = 1 trường khác ID
    ];

    function applyHideNameColumn() {
        const frappeObj = window.frappe;
        if (!frappeObj) {
            return false;
        }

        frappeObj.listview_settings = frappeObj.listview_settings || {};

        TARGET_DOCTYPES.forEach(dt => {
            const original = frappeObj.listview_settings[dt] || {};

            frappeObj.listview_settings[dt] = {
                ...original,
                hide_name_column: true,
            };
        });
        return true;
    }

    function waitAndApply() {
        if (applyHideNameColumn()) {
            return;
        }

        if (Date.now() - waitStartAt >= WAIT_TIMEOUT_MS) {
            return;
        }

        setTimeout(waitAndApply, WAIT_STEP_MS);
    }

    waitAndApply();
})();

(() => {
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

    frappe.provide("frappe.listview_settings");

    TARGET_DOCTYPES.forEach(dt => {
        const original = frappe.listview_settings[dt] || {};

        frappe.listview_settings[dt] = {
            ...original,
            hide_name_column: true,
        };
    });
})();

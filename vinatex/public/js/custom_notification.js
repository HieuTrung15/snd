// vinatex_theme/public/js/custom_notifications.js

(function () {
    // Hàm cập nhật badge theo số Notification Log chưa đọc
    function updateNotificationBadge() {
        const $btn = $('.notifications-icon');
        if (!$btn.length) return;

        frappe.call({
            method: "frappe.client.get_count",
            args: {
                doctype: "Notification Log",
                filters: {
                    for_user: frappe.session.user,
                    read: 0
                }
            },
            callback(r) {
                const count = r.message || 0;

                // Xóa badge cũ
                $btn.find('.vnt-notification-badge').remove();

                if (count > 0) {
                    // Thêm badge hiển thị số thông báo
                    $btn.append(
                        `<span class="vnt-notification-badge">${count}</span>`
                    );

                    // Đổi màu icon: bỏ xám, chuyển đỏ
                    $btn.removeClass('text-muted').addClass('text-danger');
                } else {
                    // Không có thông báo → icon xám
                    $btn.addClass('text-muted').removeClass('text-danger');
                }
            }
        });
    }

    function setup_custom_notifications() {
        const $btn = $('.notifications-icon');

        if (!$btn.length) {
            // Navbar chưa render xong → thử lại sau 300ms
            setTimeout(setup_custom_notifications, 300);
            return;
        }

        // 1) Thay icon SVG mặc định trong .notifications-seen & .notifications-unseen
        const customSvg = `
            <svg class="es-icon icon-sm vnt-bell" viewBox="0 0 24 24">
                <path d="M12 2 C8.7 2 6 4.7 6 8 v5.5l-1.5 2V17h15v-1.5L18 13.5V8c0-3.3-2.7-6-6-6zM10 19a2 2 0 0 0 4 0h-4z"></path>
            </svg>
        `;

        $btn.find('.notifications-seen svg, .notifications-unseen svg').remove();
        $btn.find('.notifications-seen').append(customSvg);
        $btn.find('.notifications-unseen').append(customSvg);

        // 2) Cập nhật lần đầu khi load trang
        updateNotificationBadge();

        // 3) Gắn realtime: khi Frappe bắn event "notification" → cập nhật lại
        if (frappe.realtime && frappe.realtime.on) {
            frappe.realtime.on('notification', function () {
                updateNotificationBadge();
            });
        }

        // 4) Dự phòng: mỗi 15 giây auto refresh một lần
        setInterval(updateNotificationBadge, 15000);

        // 5) QUAN TRỌNG: click vào 1 notification item → cập nhật lại ngay sau khi mark read
        // Selector này bám vào dropdown mặc định của Frappe:
        // .dropdown-notifications .notifications-list ...
        $(document).on(
            'click',
            '.dropdown-notifications .notifications-list .recent-item, .dropdown-notifications .notifications-list a',
            function () {
                // Cho server 0.5 giây để mark read, rồi sync lại badge
                setTimeout(updateNotificationBadge, 200);
            }
        );
    }

    // Chạy khi DOM đã sẵn sàng
    $(document).ready(function () {
        setup_custom_notifications();
    });
})();

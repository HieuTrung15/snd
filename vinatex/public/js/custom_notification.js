// giảm thông báo đã nhanh hơn nhưng chưa có thay đổi giao diện
// (function () {
//     // Vẽ lại badge & màu theo count
//     function renderBadge($btn, count) {
//         $btn.find('.vnt-notification-badge').remove();

//         if (count > 0) {
//             $btn.append(`<span class="vnt-notification-badge">${count}</span>`);
//             $btn.removeClass('text-muted').addClass('text-danger');
//         } else {
//             $btn.addClass('text-muted').removeClass('text-danger');
//         }
//     }

//     // Lấy số unread từ server
//     function updateNotificationBadge() {
//         const $btn = $('.notifications-icon');
//         if (!$btn.length) return;

//         frappe.call({
//             method: "frappe.client.get_count",
//             args: {
//                 doctype: "Notification Log",
//                 filters: {
//                     for_user: frappe.session.user,
//                     read: 0
//                 }
//             },
//             callback(r) {
//                 const count = r.message || 0;
//                 renderBadge($btn, count);
//             }
//         });
//     }

//     // Giảm ngay 1 đơn vị trên UI (optimistic)
//     function decreaseBadgeOnce() {
//         const $btn = $('.notifications-icon');
//         if (!$btn.length) return;

//         const $badge = $btn.find('.vnt-notification-badge');
//         if (!$badge.length) return;

//         const current = parseInt($badge.text(), 10);
//         if (isNaN(current) || current <= 0) return;

//         const next = current - 1;
//         renderBadge($btn, next);
//     }

//     // Chỉ giữ tab Notifications + thêm tab "Mark all as read" trên cùng hàng
//     function customizeNotificationDropdown() {
//         const $dd = $('.dropdown-notifications:visible');
//         if (!$dd.length) return;

//         const $tabs = $dd.find('.nav-tabs').first();
//         if (!$tabs.length) return;

//         // 1) Ẩn Events, What's New, chỉ giữ Notifications
//         $tabs.find('.nav-link').each(function () {
//             const text = ($(this).text() || '').trim();
//             if (text === 'Notifications') {
//                 $(this)
//                     .addClass('active')
//                     .attr('aria-selected', 'true');
//             } else {
//                 $(this).closest('li').addClass('d-none');
//             }
//         });

//         // 2) Chỉ hiển thị tab-pane Notifications
//         $dd.find('.tab-pane').each(function () {
//             const id = (this.id || '').toLowerCase();
//             if (id.indexOf('notification') !== -1) {
//                 $(this).addClass('active show').show();
//             } else {
//                 $(this).removeClass('active show').hide();
//             }
//         });

//         // 3) Thêm tab "Mark all as read" ở bên phải hàng tab (nếu chưa có)
//         if (!$tabs.find('.vnt-mark-all-read').length) {
//             const $markTab = $(`
//                 <li class="nav-item ms-auto vnt-mark-all-tab">
//                     <a href="#" class="nav-link vnt-mark-all-read">
//                         ${__('Mark all as read')}
//                     </a>
//                 </li>
//             `);
//             $tabs.append($markTab);
//         }

//         // 4) Ẩn icon/settings khác nếu có
//         $dd.find('.notifications-settings, .notification-settings, .btn-settings').hide();
//     }

//     function setup_custom_notifications() {
//         const $btn = $('.notifications-icon');

//         if (!$btn.length) {
//             setTimeout(setup_custom_notifications, 300);
//             return;
//         }

//         // Thay icon SVG mặc định trong .notifications-seen & .notifications-unseen
//         const customSvg = `
//             <svg class="es-icon icon-sm vnt-bell" viewBox="0 0 24 24">
//                 <path d="M12 2 C8.7 2 6 4.7 6 8 v5.5l-1.5 2V17h15v-1.5L18 13.5V8c0-3.3-2.7-6-6-6zM10 19a2 2 0 0 0 4 0h-4z"></path>
//             </svg>
//         `;

//         $btn.find('.notifications-seen svg, .notifications-unseen svg').remove();
//         $btn.find('.notifications-seen').append(customSvg);
//         $btn.find('.notifications-unseen').append(customSvg);

//         // Cập nhật lần đầu khi load trang
//         updateNotificationBadge();

//         // Realtime khi có notification mới
//         if (frappe.realtime && frappe.realtime.on) {
//             frappe.realtime.on('notification', function () {
//                 updateNotificationBadge();
//             });
//         }

//         // Dự phòng: 10s refresh 1 lần
//         setInterval(updateNotificationBadge, 10000);

//         // Dropdown mở ra → custom lại UI tabs + Mark all as read
//         $(document).on('shown.bs.dropdown', '.dropdown-notifications', function () {
//             customizeNotificationDropdown();
//         });

//         // Bấm vào 1 thông báo → giảm số ngay lập tức, rồi sync lại từ server
//         $(document).on(
//             'click',
//             '.dropdown-notifications .tab-pane.active a:not(.nav-link):not(.vnt-mark-all-read)',
//             function () {
//                 decreaseBadgeOnce();                    // giảm ngay
//                 setTimeout(updateNotificationBadge, 300); // sync DB
//             }
//         );

//         // Bấm tab "Mark all as read" → mark tất cả là đã đọc + badge = 0
//         $(document).on('click', '.dropdown-notifications .vnt-mark-all-read', function (e) {
//             e.preventDefault();
//             e.stopPropagation();

//             frappe.call({
//                 method: 'frappe.desk.doctype.notification_log.notification_log.mark_all_as_read',
//                 callback() {
//                 const $btn = $('.notifications-icon');
//                 renderBadge($btn, 0);
//                 }
//             });
//         });
//     }

//     $(document).ready(function () {
//         setup_custom_notifications();
//     });
// })();

// vinatex_theme/public/js/custom_notifications.js

// Ẩn Events, What's New và icon Settings trong dropdown thông báo
$(document).on('shown.bs.dropdown', '.dropdown-notifications', function () {
    const $dd = $(this);

    // Ẩn 2 tab Events & What's New
    $dd.find('#todays_events').hide();
    $dd.find('#changelog_feed').hide();

    // Đảm bảo tab Notifications còn lại hiển thị
    $dd.find('#notifications').show();
    $dd.find('.notifications-settings, .notification-settings, .btn-settings').hide();
    $dd.find('#notifications').show();

    $(this).find('.full-log-btn').hide();
});



(function () {
    // Vẽ lại badge & màu theo count
    function renderBadge($btn, count) {
        $btn.find('.vnt-notification-badge').remove();

        if (count > 0) {
            $btn.append(`<span class="vnt-notification-badge">${count}</span>`);
            $btn.removeClass('text-muted').addClass('text-danger');
        } else {
            $btn.addClass('text-muted').removeClass('text-danger');
        }
    }

    // Lấy số unread từ server
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
                renderBadge($btn, count);
            }
        });
    }

    // Giảm ngay 1 đơn vị trên UI (optimistic)
    function decreaseBadgeOnce() {
        const $btn = $('.notifications-icon');
        if (!$btn.length) return;

        const $badge = $btn.find('.vnt-notification-badge');
        if (!$badge.length) return;

        const current = parseInt($badge.text(), 10);
        if (isNaN(current) || current <= 0) return;

        const next = current - 1;
        renderBadge($btn, next);
    }

    // Tuỳ biến dropdown:
    //  - Ẩn Events / What's New
    //  - Dùng icon #icon-mark-as-read làm nút "Mark all as read"
    function customizeNotificationDropdown() {
        const $dd = $('.dropdown-notifications:visible');
        if (!$dd.length) return;

        const $tabs = $dd.find('.nav-tabs').first();
        if ($tabs.length) {
            // 1) Chỉ giữ tab Notifications, ẩn Events / What's New
            $tabs.find('.nav-link').each(function () {
                const text = ($(this).text() || '').trim();
                if (text === 'Notifications') {
                    $(this)
                        .addClass('active')
                        .attr('aria-selected', 'true');
                } else {
                    $(this).closest('li').hide();
                }
            });
        }

        // 2) Chỉ hiển thị pane Notifications
        const $notifPane = $dd
            .find('.tab-pane')
            .filter(function () {
                const id = (this.id || '').toLowerCase();
                return id.indexOf('notification') !== -1;
            })
            .first();

        if ($notifPane.length) {
            $dd.find('.tab-pane').not($notifPane).removeClass('active show').hide();
            $notifPane.addClass('active show').show();
        }

        // 3) Tìm nút chứa icon #icon-mark-as-read và biến nó thành "Mark all as read"
        const $markBtn = $dd
            .find('button, a')
            .filter(function () {
                return $(this).find('use[href="#icon-mark-as-read"]').length > 0;
            })
            .first();

        if ($markBtn.length) {
            $markBtn.addClass('vnt-mark-all-read btn btn-sm btn-link');
            $markBtn.find('svg').remove(); // bỏ icon cũ
            $markBtn.text(__('Mark all as read'));
        }
    }

    function setup_custom_notifications() {
        const $btn = $('.notifications-icon');

        if (!$btn.length) {
            setTimeout(setup_custom_notifications, 200);
            return;
        }

        // Thay icon SVG mặc định trong .notifications-seen & .notifications-unseen
        const customSvg = `
            <svg class="es-icon icon-sm vnt-bell" viewBox="0 0 24 24">
                <path d="M12 2 C8.7 2 6 4.7 6 8 v5.5l-1.5 2V17h15v-1.5L18 13.5V8c0-3.3-2.7-6-6-6zM10 19a2 2 0 0 0 4 0h-4z"></path>
            </svg>
        `;
        $btn.find('.notifications-seen svg, .notifications-unseen svg').remove();
        $btn.find('.notifications-seen').append(customSvg);
        $btn.find('.notifications-unseen').append(customSvg);

        // Cập nhật lần đầu khi load
        updateNotificationBadge();

        // Realtime khi Frappe bắn notification mới
        if (frappe.realtime && frappe.realtime.on) {
            frappe.realtime.on('notification', function () {
                updateNotificationBadge();
            });
        }

        // Dự phòng: 10s refresh 1 lần
        setInterval(updateNotificationBadge, 1500);

        // Khi dropdown mở → ẩn Events/What's New + đổi icon ✔ thành "Mark all as read"
        $(document).on('shown.bs.dropdown', '.dropdown-notifications', function () {
            customizeNotificationDropdown();
        });

        // Bấm vào 1 thông báo → giảm số ngay, rồi sync lại
        $(document).on(
            'click',
            '.dropdown-notifications .tab-pane.active a:not(.nav-link):not(.vnt-mark-all-read)',
            function () {
                decreaseBadgeOnce();
                setTimeout(updateNotificationBadge, 1000);
            }
        );

        // Bấm "Mark all as read" (chính là icon cũ đã đổi thành text) → mark hết + badge = 0
        $(document).on('click', '.dropdown-notifications .vnt-mark-all-read', function (e) {
            e.preventDefault();
            e.stopPropagation();

            frappe.call({
                method: 'frappe.desk.doctype.notification_log.notification_log.mark_all_as_read',
                callback() {
                    const $btn = $('.notifications-icon');
                    renderBadge($btn, 0);
                }
            });
        });
    }

    $(document).ready(function () {
        setup_custom_notifications();
    });
})();

// // Tắt popup "Version Updated" khi bench migrate
// $(document).ready(function () {
//     if (frappe.realtime && frappe.realtime.off) {
//         frappe.realtime.off("version-update");
//     }
// });

// frappe.assets.check = function() {
//   // Không làm gì cả, tắt kiểm tra cập nhật
// };

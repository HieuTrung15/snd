(function () {
    const INIT_CLASS = "vnt-notif-init";
    const WAIT_TIMEOUT_MS = 10000;
    const WAIT_STEP_MS = 100;
    const waitStartAt = Date.now();

    // ✅ Bật chế độ init càng sớm càng tốt để ẩn badge gốc
    document.documentElement.classList.add(INIT_CLASS);
    document.addEventListener("DOMContentLoaded", () => {
        if (document.body) document.body.classList.add(INIT_CLASS);
    });

    function releaseInitClass() {
        document.documentElement.classList.remove(INIT_CLASS);
        if (document.body) document.body.classList.remove(INIT_CLASS);
    }

    function whenDeskReady(callback) {
        if (window.frappe && window.$) {
            callback();
            return;
        }

        if (Date.now() - waitStartAt >= WAIT_TIMEOUT_MS) {
            releaseInitClass();
            return;
        }

        setTimeout(() => whenDeskReady(callback), WAIT_STEP_MS);
    }

    whenDeskReady(() => {
        $(document).on("shown.bs.dropdown", ".dropdown-notifications", function () {
            const $dd = $(this);

            $dd.find("#todays_events").hide();
            $dd.find("#changelog_feed").hide();

            $dd.find("#notifications").show();
            $dd.find(".notifications-settings, .notification-settings, .btn-settings").hide();
            $(this).find(".full-log-btn").hide();
        });

    const OPTIMISTIC_GUARD_MS = 4000;

    // ✅ localStorage key cho “cách 2”
    const LS_KEY = "vnt_notif_unread_count";

    let inited = false;

    let inflight = false;
    let pending = false;

    // chống trừ double
    const decremented = new Set();
    let lastPointerAt = 0;
    const POINTER_GAP = 200;

    let optimisticGuard = null;

    function $btn() { return $('.notifications-icon'); }

    function finishInitUI() {
        releaseInitClass();
    }

    function saveLocalCount(count) {
        try { localStorage.setItem(LS_KEY, String(count)); } catch (e) {}
    }

    function loadLocalCount() {
        try {
            const n = parseInt(localStorage.getItem(LS_KEY) || "0", 10);
            return isNaN(n) ? null : n;
        } catch (e) {
            return null;
        }
    }

    function renderBadge(count, { save = true } = {}) {
        const $b = $btn();
        if (!$b.length) return;

        $b.find('.vnt-notification-badge').remove();

        if (count > 0) {
            $b.append(`<span class="vnt-notification-badge">${count}</span>`);
            $b.removeClass('text-muted').addClass('text-danger');
        } else {
            $b.addClass('text-muted').removeClass('text-danger');
        }

        if (save) saveLocalCount(count);

        // ✅ Sau khi đã render được số (từ local hoặc server) thì bỏ init để hiện badge
        finishInitUI();
    }

    function getBadgeCount() {
        const $b = $btn();
        // If there are multiple notification icons on the page, only
        // consider the first badge as the source of truth to avoid
        // concatenated texts like "12 11" when calling `.text()` on
        // a collection. This prevents wrong parses and duplicate
        // displays of old/new counts.
        const $badge = $b.find('.vnt-notification-badge').first();
        if (!$badge.length) return 0;
        const text = $badge.text().trim();
        const n = parseInt(text, 10);
        return isNaN(n) ? 0 : n;
    }

    // ✅ Count dùng API cache của bạn
    function updateBadgeFromServer(force = false) {
        if (inflight && !force) { pending = true; return; }
        inflight = true;
        pending = false;

        frappe.call({
            method: "vinatex.api.custom_notification.get_unread_notification_count",
            freeze: false,
            callback: (r) => {
                const count = r.message || 0;
                if (shouldIgnoreServerCount(count)) return;
                renderBadge(count, { save: true });
            },
            always: () => {
                inflight = false;
                if (pending) setTimeout(() => updateBadgeFromServer(true), 150);
            }
        });
    }

    // ✅ Invalidate cache bằng frappe.call
    function invalidateCacheSafe() {
        frappe.call({
            method: "vinatex.api.custom_notification.invalidate_unread_notification_cache",
            freeze: false
        });
    }

    function activateOptimisticGuard({ ignoreValue }) {
        if (typeof ignoreValue !== "number") {
            optimisticGuard = null;
            return;
        }
        optimisticGuard = {
            ignoreValue,
            expiresAt: Date.now() + OPTIMISTIC_GUARD_MS
        };
    }

    function shouldIgnoreServerCount(count) {
        if (!optimisticGuard) return false;

        if (Date.now() > optimisticGuard.expiresAt) {
            optimisticGuard = null;
            return false;
        }

        if (count === optimisticGuard.ignoreValue) {
            return true;
        }

        optimisticGuard = null;
        return false;
    }

    // ✅ Trừ badge ngay khi pointerdown
    function bindInstantDecrement() {
        document.addEventListener('pointerdown', function (e) {
            const a = e.target.closest('.dropdown-menu.notifications-list a.recent-item.notification-item');
            if (!a) return;

            if (e.target.closest('.mark-as-read')) return;

            const name = a.getAttribute('data-name');
            if (!name) return;

            const now = Date.now();
            if (now - lastPointerAt < POINTER_GAP) return;
            lastPointerAt = now;

            if (decremented.has(name)) return;
            decremented.add(name);

            const current = getBadgeCount();
            // Delay the visual decrement to ~0.7s after user clicks to view
            // the notification (so the detail view can open first).
            // Keep optimistic guard active immediately to avoid server
            // responses overwriting the expected behavior.
            activateOptimisticGuard({ ignoreValue: current });

            setTimeout(() => {
                const next = Math.max(current - 1, 0);
                if (current !== next) {
                    renderBadge(next, { save: true });
                }
                invalidateCacheSafe();
                setTimeout(() => updateBadgeFromServer(true), 400);
            }, 700);
        }, { capture: true });
    }

    function setup_custom_notifications() {
        if (inited) return;
        inited = true;

        const $b = $btn();
        if (!$b.length) {
            inited = false;
            setTimeout(setup_custom_notifications, 300);
            return;
        }

        // thay icon
        const customSvg = `
            <svg class="es-icon icon-sm vnt-bell" viewBox="0 0 24 24">
                <path d="M12 2 C8.7 2 6 4.7 6 8 v5.5l-1.5 2V17h15v-1.5L18 13.5V8c0-3.3-2.7-6-6-6zM10 19a2 2 0 0 0 4 0h-4z"></path>
            </svg>
        `;
        $b.find('.notifications-seen svg, .notifications-unseen svg').remove();
        $b.find('.notifications-seen').append(customSvg);
        $b.find('.notifications-unseen').append(customSvg);

        bindInstantDecrement();

        // ✅ CÁCH 2: render từ localStorage NGAY LẬP TỨC (để user thấy 12 luôn)
        const cached = loadLocalCount();
        if (cached !== null) {
            renderBadge(cached, { save: false }); // không ghi lại
        } else {
            // nếu chưa có cache, vẫn bỏ init UI để khỏi ẩn mãi
            finishInitUI();
        }

        // Sync thật từ server
        updateBadgeFromServer(true);

        // realtime
        if (frappe.realtime && frappe.realtime.on) {
            frappe.realtime.on('notification', () => updateBadgeFromServer(true));
            frappe.realtime.on('connect', () => updateBadgeFromServer(true));
        }

        // dropdown open
        $(document).on('shown.bs.dropdown', '.dropdown-notifications', function () {
            updateBadgeFromServer(true);
        });

        // Mark all as read
        $(document).on('click', '.dropdown-notifications .vnt-mark-all-read', function (e) {
            e.preventDefault();
            e.stopPropagation();

            const beforeMark = getBadgeCount();
            frappe.call({
                method: 'frappe.desk.doctype.notification_log.notification_log.mark_all_as_read',
                callback() {
                    activateOptimisticGuard({ ignoreValue: beforeMark });
                    renderBadge(0, { save: true });
                    invalidateCacheSafe();
                    setTimeout(() => updateBadgeFromServer(true), 200);
                }
            });
        });
    }

    $(document).ready(setup_custom_notifications);

    // Tắt popup "Version Updated"
    $(document).ready(function () {
        if (frappe.realtime && frappe.realtime.off) {
            frappe.realtime.off("version-update");
        }
    });

    if (frappe.assets) {
        frappe.assets.check = function () {};
    }
    });
})();

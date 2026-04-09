(function () {
  function applyTitleWrap() {
    const pt = document.querySelector('.page-head .page-title');
    if (!pt) return;
    pt.style.flexWrap = 'wrap';

    const t = pt.querySelector('.title-text');
    if (!t) return;
    t.style.display = 'block';
    t.style.whiteSpace = 'normal';
    t.style.overflow = 'visible';
    t.style.textOverflow = 'clip';
    t.style.wordBreak = 'break-word';
    t.style.maxWidth = '100%';
  }

  function bindRouteEvents() {
    if (window.frappe?.router?.on) {
      // Desk re-render header khi đổi route
      window.frappe.router.on("change", () => setTimeout(applyTitleWrap, 0));
      return;
    }

    // Fallback an toàn khi frappe/router chưa sẵn sàng
    window.addEventListener("hashchange", () => setTimeout(applyTitleWrap, 0));
  }

  // chạy lúc vừa load
  document.addEventListener('DOMContentLoaded', () => setTimeout(applyTitleWrap, 0));
  bindRouteEvents();
})();

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

  // chạy mỗi lần đổi màn (Desk re-render header khi đổi route)
  frappe.router.on('change', () => setTimeout(applyTitleWrap, 0));

  // chạy lúc vừa load
  document.addEventListener('DOMContentLoaded', () => setTimeout(applyTitleWrap, 0));
})();

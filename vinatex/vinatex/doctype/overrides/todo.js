// Client Script for Doctype: ToDo
frappe.ui.form.on('ToDo', {
  onload_post_render(frm) {
    maybe_redirect(frm);
  },
  refresh(frm) {
    maybe_redirect(frm);
  }
});

function maybe_redirect(frm) {
  // không redirect khi bản ghi mới
  if (frm.is_new()) return;

  const rt = frm.doc?.reference_type;   // lấy từ frm.doc
  const rn = frm.doc?.reference_name;   // name của chứng từ đích
  // const st = frm.doc?.status;

  if (!rt || !rn) return;

  const handle_redirect = () => {
    const meta = frappe.get_meta(rt);
    // chỉ redirect với doctype chuẩn, bỏ qua child table hoặc doctype không tồn tại
    if (!meta || meta.istable) return;
    if (!frappe.model.can_read(rt)) return;

    // Tránh vòng lặp nếu vừa quay lại từ chứng từ đích
    const prev_route = frappe.get_prev_route?.();
    if (
      prev_route &&
      prev_route[0] === 'Form' &&
      prev_route[1] === rt &&
      prev_route[2] === rn
    ) {
      return;
    }

    // defer 1 nhịp để chắc chắn UI đã sẵn sàng
    setTimeout(() => {
      frappe.set_route('Form', rt, rn);   // dùng reference_name thực tế
    }, 50);
  };

  if (frappe.get_meta(rt)) {
    handle_redirect();
  } else {
    frappe.model.with_doctype(rt, handle_redirect);
  }
}

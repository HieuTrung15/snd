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
  const st = frm.doc?.status;

  const TARGETS = ['VNT Attendance Confirm', 'VNT Business Trip Request'];

  if (!rt || !rn) return;
  if (!TARGETS.includes(rt)) return;
  if (st === 'Closed') return;

  // Tránh vòng lặp khi quay lại
  if (frappe.route_options && frappe.route_options._from_todo_redirect) return;

  // defer 1 nhịp để chắc chắn UI đã sẵn sàng
  setTimeout(() => {
    frappe.route_options = Object.assign({}, frappe.route_options, { _from_todo_redirect: 1 });
    frappe.set_route('Form', rt, rn);   // dùng reference_name thực tế, không hardcode
  }, 50);
}

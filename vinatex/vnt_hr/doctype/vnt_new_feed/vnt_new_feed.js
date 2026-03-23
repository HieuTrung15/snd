// Copyright (c) 2025, vinatex and contributors

frappe.ui.form.on("VNT New Feed", {
  refresh(frm) {
    // Không có quyền sửa bài viết thì ẩn nút gửi thông báo
    frm.toggle_display("gui_thong_bao", frm.has_perm("write"));

    // Luôn reset viewer mỗi lần refresh
    frm.trigger("render_attach");

    // Chỉ set mặc định khi là phiếu mới
    if (frm.is_new()) {
      if (!frm.doc.employee) {
        frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name")
          .then(r => r?.message?.name && frm.set_value("employee", r.message.name));
      }
      if (!frm.doc.date) {
        frm.set_value("date", frappe.datetime.now_date());
      }
    }
  },

  gui_thong_bao(frm) {
    if (frm.is_new() || !frm.doc.name) {
      frappe.msgprint(__("Vui lòng lưu bản tin trước khi gửi thông báo."));
      return;
    }

    if (frm.is_dirty()) {
      frappe.msgprint(__("Vui lòng lưu thay đổi trước khi gửi thông báo."));
      return;
    }

    if (frm.doc.da_gui_thong_bao) {
      frappe.msgprint(__("Bản tin này đã gửi thông báo trước đó."));
      return;
    }

    frappe.call({
      method: "vinatex.vnt_hr.doctype.vnt_new_feed.vnt_new_feed.send_teams_notification",
      args: { docname: frm.doc.name },
      freeze: true,
      freeze_message: __("Đang đưa tác vụ gửi MS Teams vào hàng chờ..."),
    }).then((r) => {
      const total = r?.message?.recipients_count || 0;
      const skipped = r?.message?.skipped_count || 0;
      frappe.show_alert({
        message: skipped > 0
          ? __("Đã tạo tác vụ gửi MS Teams cho {0} nhân sự (bỏ qua {1} nhân sự chưa có tài khoản hợp lệ).", [total, skipped])
          : __("Đã tạo tác vụ gửi MS Teams cho {0} nhân sự.", [total]),
        indicator: "green",
      });
      frm.reload_doc();
    }).catch(() => {
      frappe.msgprint(__("Không thể gửi thông báo MS Teams. Vui lòng kiểm tra cấu hình và thử lại."));
    });
  },

  // Khi trường attach đổi, render lại
  attach(frm) {
    frm.trigger("render_attach");
  },

  render_attach(frm) {
    const $wrap = frm.fields_dict.html?.$wrapper;
    if (!$wrap) return;

    const url = (frm.doc.attach || "").trim();

    if (!url) {
      // Không có file -> clear nội dung cũ
      $wrap.html('<p><i>Chưa có file nào được tải lên.</i></p>');
      return;
    }

    if (url.toLowerCase().endsWith(".pdf")) {
      // cache-buster để trình duyệt không giữ iframe cũ
      const bust = (url.includes("?") ? "&" : "?") + "ts=" + Date.now();
      $wrap.html(
        `<iframe src="${url}${bust}" width="100%" height="600"
          style="border:1px solid #ccc;border-radius:8px;"></iframe>`
      );
    } else {
      $wrap.html('<p><i>File này không phải PDF. Vui lòng tải file PDF để xem trực tiếp.</i></p>');
    }
  }
});

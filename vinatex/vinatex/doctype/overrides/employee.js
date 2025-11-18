frappe.ui.form.on("Employee", {
  department(frm) {
    if (frm.doc.department) {
      frappe.call({
        method: "vinatex.vinatex.doctype.overrides.employee.get_approver_by_department",
        args: {
          department: frm.doc.department
        },
        callback: function (r) {
          if (r.message) {
            frm.set_value("leave_approver", r.message);
          } else {
            frm.set_value("leave_approver", null);
          }
        }
      });
    }
  },
  validate(frm) {
    if (frm.doc.date_of_birth && frm.doc.gender) {
      frappe.call({
        method: "vinatex.vinatex.doctype.overrides.employee.get_retirement_date",
        args: {
          dob: frm.doc.date_of_birth,
          gender: frm.doc.gender
        },
        callback: function (r) {
          if (r.message) {
            frm.set_value("date_of_retirement", r.message);
          } else {
            frm.set_value("date_of_retirement", null);
          }
        }

      })
    }
  },
  onload(frm) {
    bind_contract_grid_events_once(frm);
  }
});

function bind_contract_grid_events_once(frm) {
  const grid = frm.fields_dict?.custom_vnt_contract?.grid;
  if (!grid || grid.__bound_contract_validity) return;

  // 1) Tick / Untick validity trong child
  frappe.ui.form.on(grid.doctype, "validity", (frm, cdt, cdn) => {
    const row = locals[cdt][cdn];

    // Nếu tick vào: bỏ tick các dòng khác + set ngày lên parent (gán trực tiếp, không set_value)
    if (row.validity) {
      (frm.doc.custom_vnt_contract || []).forEach(r => {
        if (r.name !== row.name && r.validity) r.validity = 0;
      });

      // chỉ gán khi khác giá trị cũ để tránh bẩn form vô cớ
      const new_end = row.to_date || null;
      if ((frm.doc.contract_end_date || null) !== new_end) {
        frm.doc.contract_end_date = new_end;
        frm.refresh_field("contract_end_date"); // chỉ refresh field đơn lẻ
      }

      // Không refresh cả grid nếu không cần
      // frm.refresh_field("custom_vnt_contract"); // tránh dùng
    } else {
      // Bỏ tick: nếu không còn dòng nào tick -> clear parent
      const still_any = (frm.doc.custom_vnt_contract || []).some(r => r.validity);
      if (!still_any && frm.doc.contract_end_date) {
        frm.doc.contract_end_date = null;
        frm.refresh_field("contract_end_date");
      }
    }
  });

  // 2) Đổi to_date trên dòng đang tick -> đồng bộ parent
  frappe.ui.form.on(grid.doctype, "to_date", (frm, cdt, cdn) => {
    const row = locals[cdt][cdn];
    if (row.validity) {
      const new_end = row.to_date || null;
      if ((frm.doc.contract_end_date || null) !== new_end) {
        frm.doc.contract_end_date = new_end;
        frm.refresh_field("contract_end_date");
      }
    }
  });

  grid.__bound_contract_validity = true; // đánh dấu đã bind 1 lần
}


frappe.ui.form.on("Employee Education", {
   custom_check: function(frm, cdt, cdn) {
      // chỉ cho phép 1 dòng được chọn
        const current_row = locals[cdt][cdn];

        if (current_row.custom_check) {
            (frm.doc.education || []).forEach(row => {
                if (row.name !== current_row.name) {
                    row.custom_check = 0;
                }
            });
            frm.refresh_field('education');
        }
    }
})

frappe.ui.form.on("VNT Employee Salary History", {
  he_so: function(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.he_so && row.muc_luong_cs_tap_doan) {
      row.muc_luong = row.he_so * row.muc_luong_cs_tap_doan;
      frm.refresh_field("custom_emp_salary_history");
    }
  },
  muc_luong_cs_tap_doan: function(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.he_so && row.muc_luong_cs_tap_doan) {
      row.muc_luong = row.he_so * row.muc_luong_cs_tap_doan;
      frm.refresh_field("custom_emp_salary_history");
    }
  }
})
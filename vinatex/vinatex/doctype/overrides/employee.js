frappe.ui.form.on("Employee", {
  refresh(frm) {
    toggle_salary_tables_visibility(frm);
    add_contract_docx_buttons(frm);
    rememberShiftGroupBaseline(frm);
  },
  first_name(frm) {
    update_employee_name(frm);
  },
  middle_name(frm) {
    update_employee_name(frm);
  },
  last_name(frm) {
    update_employee_name(frm);
  },
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
  custom_shift_group(frm) {
    return handleShiftGroupChange(
      frm,
      frappe,
      globalThis.VNTShiftGroupTransferUI,
    );
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

const SHIFT_GROUP_VOLATILE_KEYS = new Set([
  "__last_sync_on",
  "__onload",
  "__unsaved",
  "_liked_by",
  "_seen",
  "_user_tags",
]);

function captureShiftGroupBaseline(frm) {
  return {
    documentKey: shiftGroupDocumentKey(frm.doc),
    shiftGroup: frm.doc.custom_shift_group || null,
    wasUnsaved: Boolean(frm.doc.__unsaved),
    document: normalizeShiftGroupDocument(frm.doc),
  };
}

function rememberShiftGroupBaseline(frm) {
  const key = shiftGroupDocumentKey(frm.doc);
  frm.__vnt_shift_group_baselines ||= Object.create(null);
  if (!frm.__vnt_shift_group_baselines[key] || !frm.doc.__unsaved) {
    frm.__vnt_shift_group_baselines[key] = captureShiftGroupBaseline(frm);
  }
  frm.__vnt_shift_group_baseline = frm.__vnt_shift_group_baselines[key];
  return frm.__vnt_shift_group_baseline;
}

function hasNonShiftGroupChanges(baseline, doc) {
  if (!baseline?.document) return true;
  const current = normalizeShiftGroupDocument(doc);
  current.custom_shift_group = baseline.shiftGroup || null;
  return stableShiftGroupJson(current) !== stableShiftGroupJson(baseline.document);
}

async function handleShiftGroupChange(
  frm,
  frappeInstance,
  transferUI = globalThis.VNTShiftGroupTransferUI,
) {
  if (frm.__vnt_shift_group_change_in_progress) return;
  const documentKey = shiftGroupDocumentKey(frm.doc);
  const baseline =
    frm.__vnt_shift_group_baselines?.[documentKey] ||
    (frm.__vnt_shift_group_baseline?.documentKey === documentKey
      ? frm.__vnt_shift_group_baseline
      : null);
  if (!baseline) return;

  const targetShiftGroup = frm.doc.custom_shift_group || null;
  const sourceShiftGroup = baseline.shiftGroup || null;
  if (targetShiftGroup === sourceShiftGroup) return;

  frm.__vnt_shift_group_change_in_progress = true;
  try {
    await frm.set_value("custom_shift_group", sourceShiftGroup);

    const hasOtherChanges = hasNonShiftGroupChanges(baseline, frm.doc);
    if (!hasOtherChanges) {
      frm.doc.__unsaved = baseline.wasUnsaved ? 1 : 0;
      frm.refresh_header?.();
    }

    if (!targetShiftGroup) return;
    const translate = typeof __ === "function" ? __ : (value) => value;
    if (frm.is_new()) {
      frappeInstance.msgprint(
        translate("Hãy lưu hồ sơ nhân sự trước khi phân hoặc chuyển kíp."),
      );
      return;
    }
    if (!hasShiftGroupTransferRole(frappeInstance)) {
      frappeInstance.msgprint(
        translate("Bạn không có quyền phân hoặc chuyển kíp cho nhân sự."),
      );
      return;
    }
    if (hasOtherChanges) {
      frappeInstance.msgprint(
        translate(
          "Hãy lưu các thay đổi khác trên hồ sơ trước khi phân hoặc chuyển kíp.",
        ),
      );
      return;
    }
    if (!transferUI?.openTransferDialog) {
      frappeInstance.msgprint(
        translate("Không tải được chức năng chuyển kíp. Hãy tải lại trang."),
      );
      return;
    }

    transferUI.openTransferDialog({
      frappe: frappeInstance,
      employees: [frm.doc.name],
      initialTargetShiftGroup: targetShiftGroup,
      title: translate("Phân / chuyển kíp cho {0}", [
        frm.doc.employee_name || frm.doc.name,
      ]),
      onCompleted: async () => frm.reload_doc(),
    });
  } finally {
    frm.__vnt_shift_group_change_in_progress = false;
  }
}

function hasShiftGroupTransferRole(frappeInstance) {
  return ["HR User", "HR Manager", "System Manager"].some((role) =>
    frappeInstance.user.has_role(role),
  );
}

function shiftGroupDocumentKey(doc) {
  return `${doc?.doctype || "Employee"}:${doc?.name || "__new__"}`;
}

function normalizeShiftGroupDocument(value) {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeShiftGroupDocument(item));
  }
  if (!value || typeof value !== "object") return value;

  const normalized = {};
  for (const key of Object.keys(value).sort()) {
    if (SHIFT_GROUP_VOLATILE_KEYS.has(key) || key.startsWith("__")) continue;
    normalized[key] = normalizeShiftGroupDocument(value[key]);
  }
  return normalized;
}

function stableShiftGroupJson(value) {
  return JSON.stringify(value);
}

function update_employee_name(frm) {
  const employee_name = [frm.doc.first_name, frm.doc.middle_name, frm.doc.last_name]
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .join(" ");

  if ((frm.doc.employee_name || "") !== employee_name) {
    frm.set_value("employee_name", employee_name).then(() => frm.refresh_header());
  } else {
    frm.refresh_header();
  }
}

const HR_SALARY_USERS = new Set([
  "tult@vinatex.com.vn",
  "thudtx@vinatex.com.vn",
  "thaottt@vinatex.com.vn"
]);

function toggle_salary_tables_visibility(frm) {
  const can_view = can_view_salary_data(frm);
  ["custom_section_break_bywfl", "custom_emp_salary_history", "custom_section_break_0co8w", "custom_phu_cap", "custom_section_break_8zxr5", "custom_basic_salary_coefficient", "custom_allowance_coefficient_2", "custom_allowance_coefficient_1", "custom_muc_luong_pc_dang"].forEach((fieldname) => {
    if (frm.fields_dict[fieldname]) {
      frm.toggle_display(fieldname, can_view);
    }
  });
}

function can_view_salary_data(frm) {
  const user = frappe.session?.user;
  if (!user || user === "Guest") return false;
  if (user === "Administrator") return true;
  if (HR_SALARY_USERS.has(user)) return true;
  return frm.doc?.user_id && frm.doc.user_id === user;
}

function bind_contract_grid_events_once(frm) {
  const grid = frm.fields_dict?.custom_vnt_contract?.grid;
  if (!grid || grid.__bound_contract_validity) return;

  const sync_parent_employment_type = (row) => {
    const new_type = row?.type || null;
    if ((frm.doc.employment_type || null) !== new_type) {
      frm.doc.employment_type = new_type;
      frm.refresh_field("employment_type");
    }
  };

  const clear_parent_employment_type = () => {
    if (frm.doc.employment_type) {
      frm.doc.employment_type = null;
      frm.refresh_field("employment_type");
    }
  };

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

      sync_parent_employment_type(row);

      // Không refresh cả grid nếu không cần
      // frm.refresh_field("custom_vnt_contract"); // tránh dùng
    } else {
      // Bỏ tick: nếu không còn dòng nào tick -> clear parent
      const still_any = (frm.doc.custom_vnt_contract || []).some(r => r.validity);
      if (!still_any && frm.doc.contract_end_date) {
        frm.doc.contract_end_date = null;
        frm.refresh_field("contract_end_date");
      }

      if (!still_any) {
        clear_parent_employment_type();
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

  // 3) Đổi loại HĐ trên dòng đang tick -> đồng bộ Employment Type ở parent
  frappe.ui.form.on(grid.doctype, "type", (frm, cdt, cdn) => {
    const row = locals[cdt][cdn];
    if (row.validity) {
      sync_parent_employment_type(row);
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


// ===== Xuất HĐLĐ ra file Word (.docx) theo đúng print format =====
const CONTRACT_DOCX_OPTIONS = [
  ["6_thang", "HĐLĐ 6 tháng"],
  ["3_nam", "HĐLĐ 3 năm"],
  ["khoan_viec", "HĐLĐ khoán việc"],
  ["thu_viec", "HĐLĐ thử việc"],
  ["kxd", "HĐLĐ KXĐ thời hạn"],
];

function add_contract_docx_buttons(frm) {
  if (frm.is_new()) return;
  CONTRACT_DOCX_OPTIONS.forEach(([contract_type, label]) => {
    // frm.add_custom_button(label, () => download_contract_docx(frm, contract_type), __("Xuất HĐLĐ Word"));
  });
}

async function download_contract_docx(frm, contract_type) {
  const params = new URLSearchParams({ employee: frm.doc.name, contract_type });
  frappe.dom.freeze(__("Đang tạo file Word..."));
  try {
    const res = await fetch(`/api/method/vinatex.vnt_hr.contract_docx.download_contract_docx?${params}`, {
      headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const msgs = data._server_messages
        ? JSON.parse(data._server_messages).map((m) => JSON.parse(m).message)
        : [];
      frappe.msgprint(msgs.join("<br>") || __("Không tạo được file Word."));
      return;
    }
    const blob = await res.blob();
    const match = (res.headers.get("Content-Disposition") || "").match(/filename\*=UTF-8''([^;]+)/i);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = match ? decodeURIComponent(match[1]) : `${contract_type}.docx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  } finally {
    frappe.dom.unfreeze();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    captureShiftGroupBaseline,
    handleShiftGroupChange,
    hasNonShiftGroupChanges,
    rememberShiftGroupBaseline,
  };
}

// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

// Tìm phòng/ban của người chủ trì từ bảng người xử lý chính
const get_chair_department = (frm) => {
  const rows = [];
  if (Array.isArray(frm.doc.items)) rows.push(...frm.doc.items);
  if (Array.isArray(frm.doc.item2)) rows.push(...frm.doc.item2);
  if (Array.isArray(frm.doc.items4)) rows.push(...frm.doc.items4);
  const chairRow = rows.find((r) => r.chu_tri);
  return chairRow?.department || null;
};

// Không cho phép thời hạn dòng vượt quá thời hạn chung của văn bản
const item_role_label = (row) => {
  if (!row) return "nhân sự";
  if (is_checked(row.chu_tri)) return "Người chủ trì";
  if (is_checked(row.phoi_hop)) return "Người phối hợp";
  if (is_checked(row.nhan_de_biet)) return "Nhận để biết";
  return "nhân sự";
};

const get_handler_status_prev = (frm) => {
  if (frm._handlerStatusLastSaved === undefined) {
    frm._handlerStatusLastSaved = frm.doc.handler_status || null;
  }
  return frm._handlerStatusLastSaved;
};

const set_handler_status_prev = (frm, val) => {
  frm._handlerStatusLastSaved = val || null;
};

const is_checked = (val) => {
  if (val === 1 || val === true) return true;
  if (typeof val === "number") return val > 0;
  if (typeof val === "string") {
    const normalized = val.trim().toLowerCase();
    if (!normalized) return false;
    if (["1", "y", "yes", "true", "on", "checked", "t"].includes(normalized)) return true;
    if (["0", "false", "no"].includes(normalized)) return false;
    return false;
  }
  return false;
};
const is_done = (val) => (val || "").trim() === "Hoàn thành";

const normalize_label = (val) => (val || "").toString().trim().toLowerCase();
const normalize_department_name = (val) => normalize_label(val).replace(/\s*-\s*/g, "-").replace(/\s+/g, " ");

const get_section_fieldnames = (frm, sectionLabel) => {
  const metaFields = frm?.meta?.fields || [];
  const target = normalize_label(sectionLabel);
  const result = [];
  let inSection = false;

  metaFields.forEach((df) => {
    if (df.fieldtype === "Section Break") {
      if (inSection) {
        inSection = false;
        return;
      }
      inSection = normalize_label(df.label) === target;
      return;
    }
    if (!inSection) return;
    if (df.fieldtype === "Tab Break") {
      inSection = false;
      return;
    }
    if (["Column Break", "Section Break"].includes(df.fieldtype)) return;
    if (df.fieldname) result.push(df.fieldname);
  });

  return result;
};

const HDQT_MEMBER_FIELDS = [
  "thanh_vien_1",
  "thanh_vien_2",
  "thanh_vien_3",
  "thanh_vien_4",
  "thanh_vien_5",
  "thanh_vien_6",
  "thanh_vien_7",
  "deadline1",
  "deadline2",
  "deadline3",
  "deadline4",
  "deadline5",
  "deadline6",
  "deadline7",
  "y_kien_1",
  "y_kien_2",
  "y_kien_3",
  "y_kien_4",
  "y_kien_5",
  "y_kien_6",
  "y_kien_7",
  "y_kien_khac_1",
  "y_kien_khac_2",
  "y_kien_khac_3",
  "y_kien_khac_4",
  "y_kien_khac_5",
  "y_kien_khac_6",
  "y_kien_khac_7"
];

const get_handler_owner = (frm) => {
  const isInternal = is_checked(frm.doc.internal);
  const target = isInternal ? frm.doc.lead_depart : frm.doc.handler;
  return (target || "").trim();
};

// Lấy danh sách thành viên HĐQT theo lead_depart.
// Điều kiện role + phòng ban của lead được kiểm tra tập trung ở server (employee_in_hdqt).
const get_hdqt_members_by_lead = async (frm) => {
  const lead = (frm.doc.lead_depart || "").trim();
  if (!lead) return [];

  const cached = frm._hdqt_member_cache;
  if (cached?.lead === lead && Array.isArray(cached.members)) {
    return cached.members;
  }

  try {
    const r = await frappe.call({
      method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.employee_in_hdqt",
      args: { employee: lead },
    });
    const members = Array.isArray(r?.message) ? r.message : [];
    frm._hdqt_member_cache = { lead, members };
    return members;
  } catch (err) {
    // eslint-disable-next-line no-console
    frm._hdqt_member_cache = { lead, members: [] };
    return [];
  }
};

const HDQT_MAJORITY_COUNT = 4;
// 2 mã thành viên do lead_depart nhập ý kiến thay ở vòng 1 khi scic_opinion = 1.
const SCIC_MANUAL_EMPLOYEES = new Set(["VGT00068", "VGT00072"]);
// Các field nhập liệu trong items6 cần khóa theo quyền từng dòng.
const ITEMS6_LOCKABLE_FIELDS = ["opinion", "attach", "other", "deadline", "explan", "attach_doc"];
// Lead_depart được phép cập nhật 2 field này trên mọi dòng items6.
const ITEMS6_LEAD_GLOBAL_FIELDS = new Set(["explan", "attach_doc"]);
// Điều kiện hiển thị vnt_type "Nội bộ ban" theo user đăng nhập.
const VNT_TYPE_NOI_BO_BAN = "Nội bộ ban";
const LEAVE_APPROVER_L1_ROLE = "Leave Approver L1";
const VNT_DOCUMENT_MANAGER_ROLE = "VNT Document Manager";
const VNT_QLVB_ROLE = "VNT QLVB";
const LEAD_HDQT_DEPARTMENTS = new Set([normalize_department_name("Văn phòng HĐQT - VGT")]);
const MEMBER_HDQT_DEPARTMENTS = new Set([
  normalize_department_name("Hội đồng quản trị - VGT"),
  normalize_department_name("Hội đồng quản trị"),
]);

const has_full_document_access_role = () => (
  frappe.user.has_role("Administrator")
  || frappe.user.has_role("System Manager")
  || frappe.user.has_role(VNT_QLVB_ROLE)
);

const clear_scope_flags = (frm) => {
  frm._is_chair_scope_active = false;
  frm._is_handler_scope_active = false;
  frm._is_specialist_scope_active = false;
  frm._is_collab_scope_active = false;
};

const unlock_grid_for_full_access = (grid) => {
  if (!grid) return;
  grid.df.read_only = 0;
  grid.df.in_place_edit = true;
  (grid.docfields || []).forEach((df) => {
    df.read_only = 0;
    df.in_grid_editable_form = 1;
    df.in_place_edit = true;
  });
  grid.cannot_add_rows = false;
  grid.cannot_delete_rows = false;
  grid.wrapper.find("input, select, textarea, button").prop("disabled", false);
  grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").show();
  (grid.grid_rows || []).forEach((row) => {
    if (typeof row.toggle_editable === "function") {
      row.toggle_editable(true);
    }
  });
  grid.refresh();
};

const apply_full_access_edit_override = (frm) => {
  if (!has_full_document_access_role()) return;
  clear_scope_flags(frm);

  Object.keys(frm.fields_dict || {}).forEach((fieldname) => {
    const field = frm.fields_dict[fieldname];
    const df = field?.df;
    if (!df) return;
    if (["Column Break", "Section Break", "Tab Break"].includes(df.fieldtype)) return;

    frm.set_df_property(fieldname, "read_only", 0);
    frm.toggle_enable(fieldname, true);

    if (df.fieldtype === "Table") {
      unlock_grid_for_full_access(field.grid);
    } else if (typeof field.refresh === "function") {
      field.refresh();
    }
  });
};

const sync_summary_opinion = (frm) => {
  const rows = Array.isArray(frm.doc.items6) ? frm.doc.items6 : [];
  const agreeCount = rows.filter((row) => (row?.opinion || "").trim() === "Đồng ý").length;
  const disagreeCount = rows.filter((row) => (row?.opinion || "").trim() === "Không đồng ý").length;

  // Chỉ kết luận khi đạt mốc 4/7: 4 "Đồng ý" => "Đồng ý", 4 "Không đồng ý" => "Không đồng ý".
  let summary = "";
  if (agreeCount >= HDQT_MAJORITY_COUNT) summary = "Đồng ý";
  else if (disagreeCount >= HDQT_MAJORITY_COUNT) summary = "Không đồng ý";

  if ((frm.doc.summary_opinion || "") !== summary) {
    frm.set_value("summary_opinion", summary);
  }
};

const sync_hdqt_deadline_from_parent = (frm, opts = {}) => {
  // Khi chọn deadline ở form cha, đồng bộ xuống deadline của items6/items7.
  // Không khóa field con: user vẫn có thể chỉnh deadline từng dòng sau đó.
  const parentDeadline = frm.doc.deadline || null;
  if (!parentDeadline) return;
  const overwrite = opts.overwrite === true;

  const apply_table = (tableFieldname) => {
    const rows = Array.isArray(frm.doc[tableFieldname]) ? frm.doc[tableFieldname] : [];
    let changed = false;
    rows.forEach((row) => {
      if (!row) return;
      // overwrite=false: chỉ fill cho dòng chưa có deadline (vd: dòng mới thêm).
      if (!overwrite && row.deadline) return;
      if ((row.deadline || null) === parentDeadline) return;
      row.deadline = parentDeadline;
      changed = true;
    });
    if (changed) frm.refresh_field(tableFieldname);
  };

  apply_table("items6");
  apply_table("items7");
};

const set_hdqt_members_to_table = (frm, tableFieldname, members = []) => {
  if (!frm.get_field(tableFieldname)) return;
  // Chỉ mutate table khi dữ liệu thực sự đổi, tránh tình trạng form luôn "modified after load".
  const normalize = (val) => ((val === null || val === undefined) ? "" : `${val}`).trim();
  const buildRowMap = (rows = []) => {
    const map = new Map();
    rows.forEach((row) => {
      const employee = normalize(row?.employee);
      if (!employee || map.has(employee)) return;
      map.set(employee, {
        opinion: normalize(row?.opinion),
        attach: normalize(row?.attach),
        deadline: normalize(row?.deadline),
      });
    });
    return map;
  };

  // Giữ lại opinion/attach theo employee khi rebuild bảng để tránh mất dữ liệu đã nhập.
  const existingRows = Array.isArray(frm.doc[tableFieldname]) ? frm.doc[tableFieldname] : [];
  const previousByEmployee = new Map();
  existingRows.forEach((row) => {
    const employee = normalize(row?.employee);
    if (!employee || previousByEmployee.has(employee)) return;
    previousByEmployee.set(employee, {
      opinion: normalize(row.opinion),
      attach: row.attach || null,
      deadline: normalize(row.deadline),
    });
  });

  const targetRows = [];
  members.forEach((member) => {
    const employee = normalize(member?.name);
    if (!employee) return;
    const previous = previousByEmployee.get(employee);
    targetRows.push({
      employee,
      opinion: previous?.opinion || "",
      attach: previous?.attach || null,
      // Giữ deadline đã nhập tay theo employee; nếu là dòng mới thì lấy deadline cha làm mặc định.
      deadline: previous?.deadline || normalize(frm.doc.deadline),
    });
  });

  const currentMap = buildRowMap(existingRows);
  const targetMap = buildRowMap(targetRows);
  const sameRows = currentMap.size === targetMap.size
    && [...targetMap.keys()].every((employee) => {
      const current = currentMap.get(employee);
      const target = targetMap.get(employee);
      return !!current && !!target
        && current.opinion === target.opinion
        && current.attach === normalize(target.attach)
        && current.deadline === normalize(target.deadline);
    });
  if (sameRows) {
    frm.refresh_field(tableFieldname);
    return;
  }

  frm.clear_table(tableFieldname);
  targetRows.forEach((item) => {
    const row = frm.add_child(tableFieldname);
    row.employee = item.employee;
    row.opinion = item.opinion;
    row.attach = item.attach;
    row.deadline = item.deadline || null;
    // Lưu ID Employee để hợp lệ khi save, nhưng ép UI hiển thị tên nhân sự.
    const member = members.find((m) => normalize(m?.name) === item.employee);
    if (member?.employee_name) {
      frappe.utils.add_link_title("Employee", member.name, member.employee_name);
    }
  });
  frm.refresh_field(tableFieldname);
};

const set_hdqt_members = (frm, members = []) => {
  set_hdqt_members_to_table(frm, "items6", members);
  sync_summary_opinion(frm);
};

const set_scic_hdqt_members = (frm, members = []) => {
  set_hdqt_members_to_table(frm, "items7", members);
};

const filter_items6_members_by_scic = (members = [], scicEnabled = false) => {
  if (!scicEnabled) return members;
  // scic_opinion = 1: items6 bỏ 2 mã cố định, chỉ còn 5 thành viên.
  return members.filter((member) => member?.name && !SCIC_MANUAL_EMPLOYEES.has(member.name));
};

const sync_hdqt_member_tables = async (frm, members = null) => {
  const hdqtMembers = Array.isArray(members) ? members : await get_hdqt_members_by_lead(frm);
  const scicEnabled = is_checked(frm.doc.scic_opinion);

  // items6: scic=1 thì còn 5 người, scic=0 thì rollback đủ 7 người.
  set_hdqt_members(frm, filter_items6_members_by_scic(hdqtMembers, scicEnabled));

  // items7 chỉ dùng cho luồng scic=1.
  if (scicEnabled) {
    set_scic_hdqt_members(frm, hdqtMembers);
  } else {
    set_scic_hdqt_members(frm, []);
  }
};

const can_edit_items6_opinion = (row, currentEmp, leadEmp = "") => {
  if (has_full_document_access_role()) return true;
  const employee = (row?.employee || "").trim();
  if (!employee || !currentEmp) return false;
  const isOwner = employee === currentEmp;
  // Ngoại lệ: lead_depart có thể sửa dòng của 2 mã SCIC trong items6.
  const isLeadScicOverride = !!(leadEmp && currentEmp === leadEmp && SCIC_MANUAL_EMPLOYEES.has(employee));
  return isOwner || isLeadScicOverride;
};

const apply_items6_row_lock = (gridRow, canEditRow, isLeadUser) => {
  ITEMS6_LOCKABLE_FIELDS.forEach((fieldname) => {
     // Giữ nguyên rule cũ theo dòng; bổ sung quyền global cho lead_depart ở explan/attach_doc.
    const canEdit = canEditRow || (isLeadUser && ITEMS6_LEAD_GLOBAL_FIELDS.has(fieldname));
    if (typeof gridRow.toggle_editable === "function") {
      gridRow.toggle_editable(fieldname, canEdit);
    }
    const formField = gridRow.grid_form?.fields_dict?.[fieldname];
    if (formField) {
      formField.df.read_only = canEdit ? 0 : 1;
      formField.refresh();
    }
  });
};

const apply_items6_opinion_scope = async (frm) => {
  const grid = frm.fields_dict.items6?.grid;
  if (!grid) return;
  const currentEmp = await get_current_employee(frm);
  const leadEmp = (frm.doc.lead_depart || "").trim();
  const isLeadUser = !!(currentEmp && leadEmp && currentEmp === leadEmp);
  (grid.grid_rows || []).forEach((gridRow) => {
    const canEditRow = can_edit_items6_opinion(gridRow.doc, currentEmp, leadEmp);
    // Khóa toàn bộ field nhập liệu của items6 nếu không thuộc dòng được phép sửa.
    apply_items6_row_lock(gridRow, canEditRow, isLeadUser);
  });
};

const is_items7_manual_pair_completed = (frm) => {
  // Chỉ cho phép mở vòng nhập của các member còn lại khi 2 mã SCIC đã có opinion hợp lệ.
  const rows = Array.isArray(frm.doc.items7) ? frm.doc.items7 : [];
  const opinionByEmployee = new Map();
  rows.forEach((row) => {
    const employee = (row?.employee || "").trim();
    if (!employee || !SCIC_MANUAL_EMPLOYEES.has(employee)) return;
    opinionByEmployee.set(employee, normalize_label(row?.opinion));
  });
  return [...SCIC_MANUAL_EMPLOYEES].every((employee) => (
    ["đồng ý", "không đồng ý"].includes(opinionByEmployee.get(employee) || "")
  ));
};

const can_edit_items7_opinion = (row, currentEmp, leadEmp, manualPairCompleted = false) => {
  if (has_full_document_access_role()) return true;
  if (!row?.employee || !currentEmp) return false;
  // 2 mã cố định: chỉ lead_depart được sửa.
  if (SCIC_MANUAL_EMPLOYEES.has(row.employee)) {
    return !!(leadEmp && currentEmp === leadEmp);
  }
  // Các thành viên còn lại chỉ được nhập sau khi 2 mã SCIC đã có opinion.
  if (!manualPairCompleted) return false;
  // Đến vòng này, mỗi member chỉ sửa dòng của chính mình.
  return row.employee === currentEmp;
};

const apply_items7_opinion_scope = async (frm) => {
  const grid = frm.fields_dict.items7?.grid;
  if (!grid) return;
  const currentEmp = await get_current_employee(frm);
  const leadEmp = (frm.doc.lead_depart || "").trim();
  const manualPairCompleted = is_items7_manual_pair_completed(frm);
  (grid.grid_rows || []).forEach((gridRow) => {
    const canEdit = can_edit_items7_opinion(gridRow.doc, currentEmp, leadEmp, manualPairCompleted);
    if (typeof gridRow.toggle_editable === "function") {
      gridRow.toggle_editable("opinion", canEdit);
    }
    const formField = gridRow.grid_form?.fields_dict?.opinion;
    if (formField) {
      formField.df.read_only = canEdit ? 0 : 1;
      formField.refresh();
    }
  });
};

const should_show_hdqt_opinion = async (frm) => {
  const members = await get_hdqt_members_by_lead(frm);
  return members.length > 0;
};

const is_items6_opinion_completed = (frm) => {
  // Chỉ xét điều kiện hoàn tất items6 khi bật luồng SCIC.
  if (!is_checked(frm.doc.scic_opinion)) return false;
  // Chỉ hiển thị items7 khi dữ liệu đã được lưu xuống DB (đúng yêu cầu Save + F5).
  const isSavedDoc = !frm.is_new()
    && !(typeof frm.is_dirty === "function" ? frm.is_dirty() : !!frm.doc.__unsaved);
  if (!isSavedDoc) return false;
  const rows = Array.isArray(frm.doc.items6) ? frm.doc.items6 : [];
  if (!rows.length) return false;
  // "Có giá trị" nghĩa là opinion không rỗng.
  return rows.every((row) => !!normalize_label(row?.opinion));
};

const apply_items7_visibility = (frm) => {
  // items7 chỉ hiển thị khi scic_opinion = 1 và tất cả opinion ở items6 đã có giá trị.
  const shouldShow = is_items6_opinion_completed(frm);
  const round2Section = "tổng_hợp_ý_kiến_lần_2_section";
  if (frm.get_field(round2Section)) {
    frm.toggle_display(round2Section, shouldShow);
  }
  if (frm.get_field("items7")) {
    frm.toggle_display("items7", shouldShow);
  }
  return shouldShow;
};

const is_noi_bo_ban_type = (val) => normalize_label(val) === normalize_label(VNT_TYPE_NOI_BO_BAN);
const is_department_matched = (department, allowedDepartments) => allowedDepartments.has(normalize_department_name(department));

const get_current_employee_department = async (frm, employee = null) => {
  if (frm._currentEmployeeDepartment !== undefined) return frm._currentEmployeeDepartment;
  const currentEmp = employee || await get_current_employee(frm);
  if (!currentEmp) {
    frm._currentEmployeeDepartment = null;
    return null;
  }
  try {
    const r = await frappe.db.get_value("Employee", currentEmp, "department");
    frm._currentEmployeeDepartment = r?.message?.department || null;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(err);
    frm._currentEmployeeDepartment = null;
  }
  return frm._currentEmployeeDepartment;
};

const can_show_noi_bo_ban_for_current_user = async (frm) => {
  // Cache theo form để tránh gọi DB lặp lại nhiều lần khi refresh.
  if (frm._canShowNoiBoBanType !== undefined) return !!frm._canShowNoiBoBanType;

  if (has_full_document_access_role()) {
    frm._canShowNoiBoBanType = true;
    return true;
  }

  // Bắt buộc user có Employee để xác định phòng ban.
  const currentEmp = await get_current_employee(frm);
  if (!currentEmp) {
    frm._canShowNoiBoBanType = false;
    return false;
  }

  const department = await get_current_employee_department(frm, currentEmp);

  // Nhóm 1: Leave Approver L1 thuộc phòng Văn phòng HĐQT - VGT.
  const isHdqtOfficeL1 = frappe.user.has_role(LEAVE_APPROVER_L1_ROLE)
    && is_department_matched(department, LEAD_HDQT_DEPARTMENTS);

  // Nhóm 2: tất cả employee thuộc department Hội đồng quản trị.
  const isHdqtMember = is_department_matched(department, MEMBER_HDQT_DEPARTMENTS);

  // Hiển thị "Nội bộ ban" nếu thuộc 1 trong 2 nhóm trên.
  frm._canShowNoiBoBanType = isHdqtOfficeL1 || isHdqtMember;
  return !!frm._canShowNoiBoBanType;
};

const get_vnt_type_filters = (frm) => {
  // Không đủ điều kiện thì ẩn "Nội bộ ban" khỏi dropdown.
  if (frm._canShowNoiBoBanType) return {};
  return { name: ["!=", VNT_TYPE_NOI_BO_BAN] };
};

const apply_vnt_type_filter = async (frm) => {
  await can_show_noi_bo_ban_for_current_user(frm);
  // Nếu đang giữ giá trị không hợp lệ thì xóa để đảm bảo đúng rule.
  if (!frm._canShowNoiBoBanType && is_noi_bo_ban_type(frm.doc.vnt_type)) {
    frm.set_value("vnt_type", null);
  }
};

const apply_hdqt_opinion_visibility = async (frm) => {
  // Theo metadata JSON, items6 không có depends_on riêng nên cần toggle bằng JS.
  const shouldShow = await should_show_hdqt_opinion(frm);
  if (frm.get_field("hdqt_opinion")) {
    frm.toggle_display("hdqt_opinion", shouldShow);
  }
  if (frm.get_field("items6")) {
    frm.toggle_display("items6", shouldShow);
    frm.toggle_display("summary_opinion", shouldShow);
  }
  return shouldShow;
};

const toggle_process_section = (frm) => {
  const isOutgoing = (frm.doc.vnt_type || "").trim() === "Công văn đến";
  frm.toggle_display("biểu_đồ_xử_lý_section", isOutgoing);
  frm.toggle_display("html_editer", isOutgoing);
};

// Tự động điền số công văn đến tiếp theo khi chọn loại "Công văn đến" nếu docu_number đang trống.
const autofill_incoming_docu_number = async (frm) => {
  const type = (frm.doc.vnt_type || "").trim();
  if (type !== "Công văn đến") return;
  const r = await frappe.call({
    method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.get_next_incoming_docu_number",
    args: { document_date: frappe.datetime.now_date() },
  });
  const nextDocNo = (r?.message || "").trim();
  if (nextDocNo) {
    frm.set_value("docu_number", nextDocNo);
  }
};

const get_chair_status_prev = (frm) => {
  if (frm._chairStatusLastSaved === undefined) {
    frm._chairStatusLastSaved = frm.doc.chairperson_status || null;
  }
  return frm._chairStatusLastSaved;
};

const set_chair_status_prev = (frm, val) => {
  frm._chairStatusLastSaved = val || null;
};

const maybe_autofill_reference_number = async (frm, opts = {}) => {
  const type = (frm.doc.vnt_type || "").trim();
  if (type !== "Công văn đi") return;

  const department = frm.doc.department;
  if (!department) return;

  const docDate = frm.doc.document_date;
  if (!docDate) return;

  const typeDoc = (frm.doc.type_doc || "").trim();


  const currentRef = (frm.doc.reference_number || "").trim();
  const forced = opts.force === true;

  const autoKey = `${department}__${docDate}__${typeDoc}`;

  // Không đè giá trị người dùng đã nhập trừ khi trước đó là auto và đổi phòng/ban/năm
  if (currentRef && !forced) return;
  if (currentRef && forced && frm._autoRefKey === autoKey) return;

  try {
    const r = await frappe.call({
      method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.get_next_reference_number",
      args: { department, document_date: docDate, type_doc: typeDoc },
    });
    const nextRef = (r?.message || "").trim();
    if (nextRef) {
      frm._autoRefKey = autoKey;
      frm.set_value("reference_number", nextRef);
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(err);
  }
};

// Autofill reference_number cho "Quyết định" với format: {number}/QĐ-TĐDMVN
// Số tự động tăng từ 01, reset mỗi năm mới
const autofill_qd_reference_number = async (frm, opts = {}) => {
  const type = (frm.doc.vnt_type || "").trim();
  if (type !== "Quyết định") return;

  // Nếu không có ngày, auto set ngày hiện tại
  let docDate = frm.doc.document_date;
  if (!docDate) {
    docDate = frappe.datetime.now_date();
    await frm.set_value("document_date", docDate);
  }

  const currentRef = (frm.doc.reference_number || "").trim();
  const forced = opts.force === true;

  // Không đè nếu người dùng đã nhập thủ công, trừ khi force=true
  if (currentRef && !forced) return;
  if (currentRef && forced && frm._qdAutoRefKey === docDate) return;

  try {
    // Gọi backend để lấy số thứ tự tiếp theo cho năm hiện tại
    const r = await frappe.call({
      method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.get_next_qd_reference_number",
      args: { document_date: docDate },
    });
    const nextNum = (r?.message || "").trim();
    if (nextNum) {
      frm._qdAutoRefKey = docDate;
      // Format: 01/QĐ-TĐDMVN, 02/QĐ-TĐDMVN, ...
      frm.set_value("reference_number", `${nextNum}/QĐ-TĐDMVN`);
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(err);
  }
};

const row_has_role = (row) => {
  if (!row) return false;
  return ["chu_tri", "phoi_hop", "nhan_de_biet"].some((field) => is_checked(row[field]));
};

const row_requires_deadline = (row) => {
  if (!row) return false;
  return is_checked(row.chu_tri) || is_checked(row.phoi_hop);
};

const get_role_rows = (frm) => {
  const rows = [];
  if (Array.isArray(frm.doc.items)) rows.push(...frm.doc.items);
  if (Array.isArray(frm.doc.item2)) rows.push(...frm.doc.item2);
  if (Array.isArray(frm.doc.items4)) rows.push(...frm.doc.items4);
  return rows;
};

const has_any_role_row = (frm) => {
  const rows = get_role_rows(frm);
  return rows.some((r) => row_has_role(r));
};

const prune_items_without_role = (frm, tables = ["items"]) => {
  if (!Array.isArray(tables) || !tables.length) return false;
  let removedAny = false;

  tables.forEach((tableName) => {
    const rows = Array.isArray(frm.doc[tableName]) ? frm.doc[tableName] : [];
    let removed = false;
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      const row = rows[i] || {};
      if (!row_has_role(row)) {
        rows.splice(i, 1);
        removed = true;
      }
    }
    if (removed) {
      removedAny = true;
      frm.refresh_field(tableName);
    }
  });

  if (removedAny) {
    frm.doc.__unsaved = true;
    if (typeof frm.dirty === "function") {
      frm.dirty();
    }
  }
  return removedAny;
};

const all_specialists_done = (frm) => {
  // Nếu đã gán chuyên viên chính, yêu cầu trạng thái Hoàn thành; nếu chưa gán thì bỏ qua
  if (frm.doc.cv_xu_ly && !is_done(frm.doc.trang_thai_chuyen_vien_xu_ly)) return false;
  const rows = Array.isArray(frm.doc.items2) ? frm.doc.items2 : [];
  return rows.every((r) => {
    // Người phối hợp phải Hoàn thành
    if (!is_done(r.trang_thai_nguoi_phoi_hop)) return false;
    // Nếu có chuyên viên phối hợp thì yêu cầu Hoàn thành, nếu không có thì bỏ qua điều kiện này
    if (r.cv_xu_ly && !is_done(r.trang_thai_cv_xu_ly)) return false;
    return true;
  });
};

const validate_handler_status_preconditions = (frm) => {
  const rows = get_role_rows(frm);
  const picked = rows.filter((r) => row_has_role(r));

  if (!picked.length) {
    return { ok: false, message: "Vui lòng chọn ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết trước khi cập nhật Trạng thái Lãnh đạo Tập Đoàn." };
  }

  const needDeadlineRows = rows.filter((r) => row_requires_deadline(r));
  const missingDeadlineIdx = needDeadlineRows.findIndex((r) => !r.deadline);
  if (missingDeadlineIdx !== -1) {
    return { ok: false, message: "Dòng đã chọn vai trò chưa có Thời hạn hoàn thành. Vui lòng nhập trước khi cập nhật Trạng thái Lãnh đạo Tập Đoàn." };
  }

  return { ok: true };
};

const ensure_collab_not_done_before_specialist = (cdt, cdn) => {
  const row = (locals[cdt] && locals[cdt][cdn]) || null;
  if (!row) return;
  if (!row.cv_xu_ly) return; // Nếu chưa giao chuyên viên phối hợp, cho phép Người phối hợp tự hoàn thành
  if ((row.trang_thai_nguoi_phoi_hop || "").trim() !== "Hoàn thành") return;
  if ((row.trang_thai_cv_xu_ly || "").trim() === "Hoàn thành") return;

  frappe.msgprint("Người phối hợp chỉ được chọn Hoàn thành sau khi Chuyên viên xử lý đã Hoàn thành.");
  frappe.model.set_value(cdt, cdn, "trang_thai_nguoi_phoi_hop", "Đang xử lý");
};

const ensure_spec_deadline_within_collab = (cdt, cdn) => {
  const row = (locals[cdt] && locals[cdt][cdn]) || null;
  if (!row || !row.deadline2 || !row.deadline1) return;
  if (frappe.datetime.get_diff(row.deadline2, row.deadline1) > 0) {
    frappe.msgprint("Thời hạn Chuyên viên xử lý không được muộn hơn thời hạn Người phối hợp.");
    frappe.model.set_value(cdt, cdn, "deadline2", null);
  }
};

const ensure_handler_status_require_roles = (frm) => {
  if (!frm.doc.handler_status) return true;
  if (has_any_role_row(frm)) return true;
  frappe.msgprint("Vui lòng chọn ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết trước khi cập nhật Trạng thái Lãnh đạo Tập Đoàn.");
  frm.set_value("handler_status", null);
  return false;
};

const hide_legacy_fields = (frm) => {
  ["legacy_id", "list_title", "source_url"].forEach((field) => {
    if (frm.get_field(field)) {
      frm.set_df_property(field, "hidden", 1);
    }
  });
};

const get_current_employee = async (frm) => {
  if (frm._currentEmployee !== undefined) return frm._currentEmployee;
  try {
    const r = await frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name");
    frm._currentEmployee = r?.message?.name || null;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(err);
    frm._currentEmployee = null;
  }
  return frm._currentEmployee;
};

const is_collab_user = async (frm, currentEmp) => {
  const employee = currentEmp || (await get_current_employee(frm));
  if (!employee) return false;
  const rows = Array.isArray(frm.doc.items2) ? frm.doc.items2 : [];
  if (rows.some((row) => row.nguoi_phoi_hop === employee)) return true;
  const mainRows = get_role_rows(frm);
  return mainRows.some((row) => is_checked(row.phoi_hop) && row.employee === employee);
};

const patch_scroll_to_field = (frm) => {
  if (frm._vntScrollToFieldPatched) return;
  if (typeof frm.scroll_to_field !== "function") return;
  const original = frm.scroll_to_field.bind(frm);
  frm.scroll_to_field = (fieldname, focus = true) => {
    const field = frm.get_field(fieldname);
    const $wrapper = field?.$wrapper;
    if (!$wrapper || typeof $wrapper.find !== "function" || typeof $wrapper.closest !== "function") {
      return false;
    }
    try {
      return original(fieldname, focus);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("scroll_to_field failed", err);
      return false;
    }
  };
  frm._vntScrollToFieldPatched = true;
};

const can_view_handler_controls = async (frm) => {
  const isIncoming = (frm.doc.vnt_type || "").trim() === "Công văn đến";
  if (!isIncoming) return true;

  const handler = get_handler_owner(frm);
  if (!handler) return true; // chưa giao lãnh đạo -> cho xem để hiểu cần giao

  if (has_full_document_access_role()) {
    return true;
  }

  const currentEmp = frm._currentEmployee || (await get_current_employee(frm));
  return !!(currentEmp && handler === currentEmp);
};

const refresh_handler_controls_visibility = async (frm) => {
  const shouldShow = await can_view_handler_controls(frm);
  ["handler_status", "is_handler_status"].forEach((fieldname) => {
    frm.set_df_property(fieldname, "hidden", shouldShow ? 0 : 1);
  });
};

const set_handler_editable = (frm, enabled, opts = {}) => {
  if (frm._is_chair_scope_active || frm._is_handler_scope_active || frm._is_specialist_scope_active || frm._is_collab_scope_active) return; // Đang khóa form, bỏ qua
  const allowItems = opts.allowItems !== undefined ? opts.allowItems : enabled;
  const allowItem2 = opts.allowItem2 !== undefined ? opts.allowItem2 : enabled;
  const allowItems4 = opts.allowItems4 !== undefined ? opts.allowItems4 : false;
  const allowItems5 = opts.allowItems5 !== undefined ? opts.allowItems5 : false;
  const allowHdqtOpinion = opts.allowHdqtOpinion !== undefined ? opts.allowHdqtOpinion : enabled;
  frm.toggle_enable("y_kien_ld_td", enabled);
  frm.toggle_enable("handler_status", enabled);
  frm.toggle_enable("y_kien_ld_td", enabled);
  frm.toggle_enable("is_handler_status", enabled);
  frm.toggle_enable("hdqt_opinion", allowHdqtOpinion);
  frm.toggle_enable("deadline", !!(allowItems || allowItem2));
  const grid = frm.fields_dict.items?.grid;
  frm.set_df_property("items", "read_only", allowItems ? 0 : 1);
  if (grid) {
    grid.cannot_add_rows = !allowItems;
    grid.cannot_delete_rows = !allowItems;
    grid.refresh();
  }
  const grid2 = frm.fields_dict.item2?.grid;
  frm.set_df_property("item2", "read_only", allowItem2 ? 0 : 1);
  if (grid2) {
    grid2.cannot_add_rows = !allowItem2;
    grid2.cannot_delete_rows = !allowItem2;
    grid2.refresh();
  }
  const gridItems4 = frm.fields_dict.items4?.grid;
  frm.set_df_property("items4", "read_only", allowItems4 ? 0 : 1);
  if (gridItems4) {
    gridItems4.cannot_add_rows = !allowItems4;
    gridItems4.cannot_delete_rows = !allowItems4;
    gridItems4.refresh();
  }
  const gridItems5 = frm.fields_dict.items5?.grid;
  frm.set_df_property("items5", "read_only", allowItems5 ? 0 : 1);
  if (gridItems5) {
    gridItems5.cannot_add_rows = !allowItems5;
    gridItems5.cannot_delete_rows = !allowItems5;
    gridItems5.refresh();
  }
};

const enforce_chair_scope = async (frm) => {
  if (has_full_document_access_role()) {
    clear_scope_flags(frm);
    apply_full_access_edit_override(frm);
    return;
  }

  const isIncoming = (frm.doc.vnt_type || "").trim() === "Công văn đến";
  if (!isIncoming) {
    frm._is_chair_scope_active = false;
    return;
  }

  const currentEmp = frm._currentEmployee || (await get_current_employee(frm));
  if (!currentEmp || frm.doc.nguoi_chu_tri !== currentEmp) {
    frm._is_chair_scope_active = false;
    return;
  }

  frm._is_chair_scope_active = true;

  const allowed = new Set(["chairperson_status", "y_kien_chu_tri", "cv_xu_ly", "deadline_cv_xu_ly", "items3"]);

  Object.keys(frm.fields_dict || {}).forEach((fieldname) => {
    const field = frm.fields_dict[fieldname];
    const df = field?.df;
    if (!df) return;
    if (["Column Break", "Section Break", "Tab Break"].includes(df.fieldtype)) return;
    const isAllowed = allowed.has(fieldname);
    frm.set_df_property(fieldname, "read_only", isAllowed ? 0 : 1);
    frm.toggle_enable(fieldname, isAllowed);
    if (!isAllowed && typeof field.refresh === "function") {
      field.refresh();
    }
  });

  // Khóa thao tác thêm/xóa cho các bảng không được phép
  const lockGrid = (grid) => {
    if (!grid) return;
    grid.df.read_only = 1;
    grid.df.in_place_edit = false;
    (grid.docfields || []).forEach((df) => {
      df.read_only = 1;
      df.in_grid_editable_form = 0;
      df.in_place_edit = false;
    });
    grid.cannot_add_rows = true;
    grid.cannot_delete_rows = true;
    grid.wrapper.find("input, select, textarea, button").prop("disabled", true);
    grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
    if (grid.grid_rows) {
      grid.grid_rows.forEach((row) => {
        if (typeof row.toggle_editable === "function") {
          row.toggle_editable(false);
        }
      });
    }
    grid.refresh();
  };
  lockGrid(frm.fields_dict.items?.grid);
  lockGrid(frm.fields_dict.item2?.grid);
  lockGrid(frm.fields_dict.items2?.grid);
  lockGrid(frm.fields_dict.item4?.grid);
};

const enforce_handler_scope = async (frm) => {
  if (has_full_document_access_role()) {
    clear_scope_flags(frm);
    apply_full_access_edit_override(frm);
    return;
  }

  if (frm._is_chair_scope_active) {
    frm._is_handler_scope_active = false;
    return; // Ưu tiên khóa của Chủ trì
  }

  const isIncoming = (frm.doc.vnt_type || "").trim() === "Công văn đến";
  if (!isIncoming) {
    frm._is_handler_scope_active = false;
    return;
  }

  const currentEmp = frm._currentEmployee || (await get_current_employee(frm));
  const handlerOwner = get_handler_owner(frm);
  if (!currentEmp || handlerOwner !== currentEmp) {
    frm._is_handler_scope_active = false;
    return;
  }

  frm._is_handler_scope_active = true;

  const isInternal = is_checked(frm.doc.internal);
  const trinhDuyetFields = get_section_fieldnames(frm, "Trình duyệt");
  const allowed = new Set([
    "y_kien_ld_td",
    "handler_status",
    "is_handler_status",
    "hdqt_opinion",
    ...HDQT_MEMBER_FIELDS,
    ...trinhDuyetFields,
    ...(isInternal ? ["lead_depart", "send_boss", "items4", "items5"] : ["items", "item2", "deadline"])
  ]);
  const leaderOwner = (frm.doc.lanh_dao_tap_doan || "").trim();
  const canEditLeaderFields = !!(currentEmp && leaderOwner && currentEmp === leaderOwner);
  if (!canEditLeaderFields) {
    allowed.delete("y_kien_lanh_dao_tap_doan");
    allowed.delete("trang_thai_lanh_dao_tap_doan");
  }

  Object.keys(frm.fields_dict || {}).forEach((fieldname) => {
    const field = frm.fields_dict[fieldname];
    const df = field?.df;
    if (!df) return;
    if (["Column Break", "Section Break", "Tab Break"].includes(df.fieldtype)) return;
    const isAllowed = allowed.has(fieldname);
    frm.set_df_property(fieldname, "read_only", isAllowed ? 0 : 1);
    frm.toggle_enable(fieldname, isAllowed);
    if (!isAllowed && typeof field.refresh === "function") {
      field.refresh();
    }
  });

  const lockGrid = (grid, forceReadOnly = true) => {
    if (!grid) return;
    if (!allowed.has(grid.df?.fieldname) || forceReadOnly) {
      grid.df.read_only = 1;
      grid.df.in_place_edit = false;
      (grid.docfields || []).forEach((df) => {
        df.read_only = 1;
        df.in_grid_editable_form = 0;
        df.in_place_edit = false;
      });
      grid.cannot_add_rows = true;
      grid.cannot_delete_rows = true;
      grid.wrapper.find("input, select, textarea, button").prop("disabled", true);
      grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
      if (grid.grid_rows) {
        grid.grid_rows.forEach((row) => {
          if (typeof row.toggle_editable === "function") {
            row.toggle_editable(false);
          }
        });
      }
    } else {
      grid.df.read_only = 0;
      grid.cannot_add_rows = false;
      grid.cannot_delete_rows = false;
      grid.wrapper.find("input, select, textarea, button").prop("disabled", false);
      grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").show();
    }
    grid.refresh();
  };

  lockGrid(frm.fields_dict.items?.grid, false); // items được phép sửa khi không nội bộ
  lockGrid(frm.fields_dict.item2?.grid, false);
  lockGrid(frm.fields_dict.items4?.grid, false);
  lockGrid(frm.fields_dict.items5?.grid, false);
  lockGrid(frm.fields_dict.items2?.grid);
  lockGrid(frm.fields_dict.items3?.grid);
  lockGrid(frm.fields_dict.item4?.grid);
};

const enforce_specialist_scope = async (frm) => {
  if (has_full_document_access_role()) {
    clear_scope_flags(frm);
    apply_full_access_edit_override(frm);
    return;
  }

  if (frm._is_chair_scope_active || frm._is_handler_scope_active) {
    frm._is_specialist_scope_active = false;
    return; // Ưu tiên khóa của Chủ trì/Lãnh đạo
  }

  const isIncoming = (frm.doc.vnt_type || "").trim() === "Công văn đến";
  if (!isIncoming) {
    frm._is_specialist_scope_active = false;
    return;
  }

  const currentEmp = frm._currentEmployee || (await get_current_employee(frm));
  if (!currentEmp || frm.doc.cv_xu_ly !== currentEmp) {
    frm._is_specialist_scope_active = false;
    return;
  }

  frm._is_specialist_scope_active = true;

  const allowed = new Set(["trang_thai_chuyen_vien_xu_ly", "y_kien_chuyen_vien_xu_ly", "items3"]);

  Object.keys(frm.fields_dict || {}).forEach((fieldname) => {
    const field = frm.fields_dict[fieldname];
    const df = field?.df;
    if (!df) return;
    if (["Column Break", "Section Break", "Tab Break"].includes(df.fieldtype)) return;
    const isAllowed = allowed.has(fieldname);
    frm.set_df_property(fieldname, "read_only", isAllowed ? 0 : 1);
    frm.toggle_enable(fieldname, isAllowed);
    if (!isAllowed && typeof field.refresh === "function") {
      field.refresh();
    }
  });

  const lockGrid = (grid, isAllowedGrid) => {
    if (!grid) return;
    if (isAllowedGrid) {
      grid.df.read_only = 0;
      grid.df.in_place_edit = true;
      grid.cannot_add_rows = false;
      grid.cannot_delete_rows = false;
      grid.wrapper.find("input, select, textarea, button").prop("disabled", false);
      grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").show();
    } else {
      grid.df.read_only = 1;
      grid.df.in_place_edit = false;
      (grid.docfields || []).forEach((df) => {
        df.read_only = 1;
        df.in_grid_editable_form = 0;
        df.in_place_edit = false;
      });
      grid.cannot_add_rows = true;
      grid.cannot_delete_rows = true;
      grid.wrapper.find("input, select, textarea, button").prop("disabled", true);
      grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
      if (grid.grid_rows) {
        grid.grid_rows.forEach((row) => {
          if (typeof row.toggle_editable === "function") {
            row.toggle_editable(false);
          }
        });
      }
    }
    grid.refresh();
  };

  lockGrid(frm.fields_dict.items?.grid, false);
  lockGrid(frm.fields_dict.item2?.grid, false);
  lockGrid(frm.fields_dict.items2?.grid, false);
  lockGrid(frm.fields_dict.items3?.grid, true); // items3 được phép sửa
  lockGrid(frm.fields_dict.item4?.grid, false);
};

const enforce_collab_scope = async (frm) => {
  if (has_full_document_access_role()) {
    clear_scope_flags(frm);
    apply_full_access_edit_override(frm);
    return;
  }

  if (frm._is_chair_scope_active || frm._is_handler_scope_active || frm._is_specialist_scope_active) {
    frm._is_collab_scope_active = false;
    return; // Ưu tiên khóa cao hơn
  }

  const isIncoming = (frm.doc.vnt_type || "").trim() === "Công văn đến";
  if (!isIncoming) {
    frm._is_collab_scope_active = false;
    return;
  }

  const currentEmp = frm._currentEmployee || (await get_current_employee(frm));
  const rows = Array.isArray(frm.doc.items2) ? frm.doc.items2 : [];
  const myRows = rows.filter((row) => row.nguoi_phoi_hop === currentEmp);
  if (!currentEmp || !myRows.length) {
    frm._is_collab_scope_active = false;
    return;
  }

  frm._is_collab_scope_active = true;

  const allowed = new Set(["items2", "item4"]);

  Object.keys(frm.fields_dict || {}).forEach((fieldname) => {
    const field = frm.fields_dict[fieldname];
    const df = field?.df;
    if (!df) return;
    if (["Column Break", "Section Break", "Tab Break"].includes(df.fieldtype)) return;
    const isAllowed = allowed.has(fieldname);
    frm.set_df_property(fieldname, "read_only", isAllowed ? 0 : 1);
    frm.toggle_enable(fieldname, isAllowed);
    if (!isAllowed && typeof field.refresh === "function") {
      field.refresh();
    }
  });

  // Khóa các bảng khác
  const lockGrid = (grid) => {
    if (!grid) return;
    grid.df.read_only = 1;
    grid.df.in_place_edit = false;
    (grid.docfields || []).forEach((df) => {
      df.read_only = 1;
      df.in_grid_editable_form = 0;
      df.in_place_edit = false;
    });
    grid.cannot_add_rows = true;
    grid.cannot_delete_rows = true;
    grid.wrapper.find("input, select, textarea, button").prop("disabled", true);
    grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
    if (grid.grid_rows) {
      grid.grid_rows.forEach((row) => {
        if (typeof row.toggle_editable === "function") {
          row.toggle_editable(false);
        }
      });
    }
    grid.refresh();
  };
  lockGrid(frm.fields_dict.items?.grid);
  lockGrid(frm.fields_dict.item2?.grid);
  lockGrid(frm.fields_dict.items3?.grid);

  // items4: cho phép sửa
  const gridItem4 = frm.fields_dict.item4?.grid;
  if (gridItem4) {
    gridItem4.df.read_only = 0;
    gridItem4.df.in_place_edit = true;
    gridItem4.cannot_add_rows = false;
    gridItem4.cannot_delete_rows = false;
    gridItem4.wrapper.find("input, select, textarea, button").prop("disabled", false);
    gridItem4.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").show();
    gridItem4.refresh();
  }

  // items2: chỉ cho chỉnh trường được phép và chỉ trên dòng của mình
  const gridCollab = frm.fields_dict.items2?.grid;
  if (gridCollab) {
    const allowedChild = new Set(["trang_thai_nguoi_phoi_hop", "y_kien_nguoi_phoi_hop", "cv_xu_ly", "deadline2"]);
    gridCollab.df.read_only = 0;
    gridCollab.df.in_place_edit = true;
    gridCollab.cannot_add_rows = true;
    gridCollab.cannot_delete_rows = true;
    gridCollab.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
    (gridCollab.docfields || []).forEach((df) => {
      const canEdit = allowedChild.has(df.fieldname);
      df.read_only = canEdit ? 0 : 1;
      df.in_grid_editable_form = canEdit ? 1 : 0;
      df.in_place_edit = canEdit;
    });
    gridCollab.refresh();
    if (gridCollab.grid_rows) {
      gridCollab.grid_rows.forEach((row) => {
        const mine = row.doc?.nguoi_phoi_hop === currentEmp;
        row.toggle_editable(!!mine);
        if (!mine) {
          row.row && row.row.find("input, select, textarea, button").prop("disabled", true);
        } else {
          row.row && row.row.find("input, select, textarea, button").prop("disabled", false);
        }
      });
    }
  }
};

const apply_handler_edit_lock = async (frm) => {
  if (has_full_document_access_role()) {
    clear_scope_flags(frm);
    set_handler_editable(frm, true, {
      allowItems: true,
      allowItem2: true,
      allowItems4: true,
      allowItems5: true,
      allowHdqtOpinion: true,
    });
    apply_full_access_edit_override(frm);
    return;
  }

  const isIncoming = (frm.doc.vnt_type || "").trim() === "Công văn đến";
  if (!isIncoming) {
    set_handler_editable(frm, true);
    return;
  }

  const currentEmp = await get_current_employee(frm);
  const isInternal = is_checked(frm.doc.internal);
  const handlerOwner = get_handler_owner(frm);
  const canEdit = isInternal
    ? !!(currentEmp && handlerOwner && handlerOwner === currentEmp)
    : (!handlerOwner || (currentEmp && handlerOwner === currentEmp));
  const allowItems4 = isInternal && !!canEdit;
  const allowItems5 = isInternal && !!canEdit;
  set_handler_editable(frm, !!canEdit, { allowItems: !isInternal && !!canEdit, allowItem2: !isInternal && !!canEdit, allowItems4, allowItems5, allowHdqtOpinion: !!canEdit });
  await enforce_handler_scope(frm);
};

const set_creator_editable = (frm, enabled) => {
  if (frm._is_chair_scope_active || frm._is_handler_scope_active || frm._is_specialist_scope_active || frm._is_collab_scope_active) return; // Đang khóa form, bỏ qua
  const fields = ["type", "vnt_type", "sender", "handler", "document_date", "received_date", "deadline", "reference_number", "summary", "attach"];
  fields.forEach((field) => frm.toggle_enable(field, enabled));
};

const apply_creator_edit_lock = async (frm) => {
  if (has_full_document_access_role()) {
    clear_scope_flags(frm);
    set_creator_editable(frm, true);
    apply_full_access_edit_override(frm);
    return;
  }

  if (frappe.user.has_role(VNT_DOCUMENT_MANAGER_ROLE)) {
    set_creator_editable(frm, true);
    return;
  }

  const creator = frm.doc.employee || null;
  if (!creator) {
    set_creator_editable(frm, true);
    return;
  }
  const currentEmp = await get_current_employee(frm);
  const canEdit = currentEmp && creator === currentEmp;
  set_creator_editable(frm, !!canEdit);
};

const set_chair_editable = (frm, enabled, opts = {}) => {
  const allowItems2 = opts.allowItems2 !== undefined ? opts.allowItems2 : enabled;
  const allowItem4 = opts.allowItem4 !== undefined ? opts.allowItem4 : enabled;
  const fields = ["chairperson_status", "cong_van_di", "y_kien_chu_tri", "deadline_cv_xu_ly", "cv_xu_ly"];
  fields.forEach((field) => frm.toggle_enable(field, enabled));

  const grid = frm.fields_dict.items3?.grid;
  frm.set_df_property("items3", "read_only", enabled ? 0 : 1);
  if (grid) {
    grid.cannot_add_rows = !enabled;
    grid.cannot_delete_rows = !enabled;
    grid.refresh();
  }

  const gridCollab = frm.fields_dict.items2?.grid;
  frm.set_df_property("items2", "read_only", allowItems2 ? 0 : 1);
  if (gridCollab) {
    gridCollab.df.read_only = allowItems2 ? 0 : 1;
    gridCollab.cannot_add_rows = !allowItems2;
    gridCollab.cannot_delete_rows = !allowItems2;
    gridCollab.refresh();
  }

  const gridItem4 = frm.fields_dict.item4?.grid;
  frm.set_df_property("item4", "read_only", allowItem4 ? 0 : 1);
  if (gridItem4) {
    gridItem4.df.read_only = allowItem4 ? 0 : 1;
    gridItem4.cannot_add_rows = !allowItem4;
    gridItem4.cannot_delete_rows = !allowItem4;
    gridItem4.refresh();
  }
};

const apply_chair_edit_lock = async (frm) => {
  if (has_full_document_access_role()) {
    clear_scope_flags(frm);
    set_chair_editable(frm, true, { allowItems2: true, allowItem4: true });
    apply_full_access_edit_override(frm);
    return;
  }

  const chair = frm.doc.nguoi_chu_tri || null;
  const specialist = frm.doc.cv_xu_ly || null;
  if (!chair && !specialist) {
    set_chair_editable(frm, false);
    frm._is_chair_scope_active = false;
    return;
  }
  const currentEmp = await get_current_employee(frm);
  const isChairUser = currentEmp && chair === currentEmp;
  const canEditHeader = currentEmp && chair === currentEmp;
  const isCollabUser = await is_collab_user(frm, currentEmp);
  const allowItems2 = canEditHeader ? false : !!isCollabUser; // Người chủ trì chỉ được sửa các field cho phép, không sửa bảng phối hợp
  const allowItem4 = canEditHeader ? false : false; // Không cho sửa item4 khi là chủ trì/chuyên viên chính
  set_chair_editable(frm, !!canEditHeader, { allowItems2, allowItem4 });
  if (isChairUser) {
    await enforce_chair_scope(frm);
  } else {
    frm._is_chair_scope_active = false;
  }
};

// Đảm bảo chỉ có duy nhất một dòng được chọn Chủ trì
const ensure_single_chair_row = (frm, cdt, cdn) => {
  const row = (locals[cdt] && locals[cdt][cdn]) || null;
  if (!row || !row.chu_tri) return;

  const rows = [];
  if (Array.isArray(frm.doc.items)) rows.push(...frm.doc.items);
  if (Array.isArray(frm.doc.item2)) rows.push(...frm.doc.item2);
  if (Array.isArray(frm.doc.items4)) rows.push(...frm.doc.items4);
  rows.forEach((r) => {
    if (r.name !== row.name && r.chu_tri) {
      frappe.model.set_value(r.doctype || cdt, r.name, "chu_tri", 0);
    }
  });
};

// Mỗi dòng chỉ được chọn một vai trò
const enforce_single_role = (cdt, cdn, pickedField) => {
  if (!cdt || !cdn || !pickedField) return;
  const row = (locals[cdt] && locals[cdt][cdn]) || null;
  if (!row || !row[pickedField]) return;

  ["chu_tri", "phoi_hop", "nhan_de_biet"].forEach((field) => {
    if (field !== pickedField && row[field]) {
      frappe.model.set_value(cdt, cdn, field, 0);
    }
  });
};

const ensure_item_deadline_within_parent = (frm, cdt, cdn) => {
  if (!frm.doc.deadline || !cdt || !cdn) return;
  const row = (locals[cdt] && locals[cdt][cdn]) || null;
  if (!row || !row.deadline) return;

  if (frappe.datetime.get_diff(row.deadline, frm.doc.deadline) > 0) {
    const typeLabel = item_role_label(row);
    frappe.msgprint(`Thời hạn hoàn thành của ${typeLabel} không được muộn hơn thời hạn xử lý văn bản ${frm.doc.deadline}`);
    frappe.model.set_value(cdt, cdn, "deadline", null);
  }
};

const ensure_spec_deadline_not_after_chair = (frm) => {
  if (!frm.doc.deadline_cv_xu_ly || !frm.doc.deadline_chu_tri2) return true;
  if (frappe.datetime.get_diff(frm.doc.deadline_cv_xu_ly, frm.doc.deadline_chu_tri2) > 0) {
    frappe.msgprint("Thời hạn Chuyên viên xử lý không được muộn hơn thời hạn Người chủ trì.");
    frm.set_value("deadline_cv_xu_ly", null);
    return false;
  }
  return true;
};

const find_late_item_deadline = (frm) => {
  if (!frm.doc.deadline) return null;
  const rows = Array.isArray(frm.doc.items) ? frm.doc.items : [];
  const idx = rows.findIndex((row) => row.deadline && frappe.datetime.get_diff(row.deadline, frm.doc.deadline) > 0);
  if (idx === -1) return null;
  return { row: rows[idx], idx: idx + 1, typeLabel: item_role_label(rows[idx]) };
};

const find_multiple_chair = (frm) => {
  const rows = [];
  if (Array.isArray(frm.doc.items)) rows.push(...frm.doc.items);
  if (Array.isArray(frm.doc.item2)) rows.push(...frm.doc.item2);
  if (Array.isArray(frm.doc.items4)) rows.push(...frm.doc.items4);
  const picked = rows.filter((r) => r.chu_tri);
  if (picked.length <= 1) return null;
  return picked;
};

frappe.ui.form.on("VNT Document Management", {
  async onload (frm) {
    frm.set_query('lead_depart', () => {
      return {
        filters: {
          status: 'Active',
          custom_designation_group: "Lãnh đạo cấp trung",
        }
      }
    });
    frm.set_df_property("lanh_dao_tap_doan", "ignore_user_permissions", 1);
    frm.set_query("lanh_dao_tap_doan", () => {
      return {
        query: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.employee_query_all"
      };
    });
    // Filter vnt_type theo user đăng nhập:
    // chỉ hiện "Nội bộ ban" cho:
    // 1) Leave Approver L1 của Văn phòng HĐQT - VGT; hoặc
    // 2) toàn bộ employee thuộc Hội đồng quản trị.
    frm.set_query("vnt_type", () => ({
      filters: get_vnt_type_filters(frm),
    }));
    await apply_vnt_type_filter(frm);
  },
  async lead_depart(frm) {
    const lead_id = (frm.doc.lead_depart || "").trim();
    frm._hdqt_member_cache = null;

    frm.clear_table("items4");
    if (lead_id) {
      try {
        const r = await frappe.call({
          method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.employee_in_department",
          args: { employee: lead_id }
        });
        const employees = Array.isArray(r?.message) ? r.message : [];
        const filtered_employees = employees.filter((item) => (
          item.name !== lead_id && item.designation !== "Trưởng ban"
        ));
        filtered_employees.forEach((item) => {
          const row = frm.add_child("items4");
          row.employee = item.name;
          row.department = item.department;
        });
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error(err);
      }
    }
    frm.refresh_field("items4");

    // Sync lại 2 bảng HĐQT theo scic_opinion:
    // - scic=1: items6 còn 5, items7 giữ 7
    // - scic=0: items6 rollback 7, items7 rỗng
    const hdqtMembers = await get_hdqt_members_by_lead(frm);
    await sync_hdqt_member_tables(frm, hdqtMembers);
    // Nếu đã có deadline cha thì fill deadline mặc định cho các dòng mới ở items6/items7.
    sync_hdqt_deadline_from_parent(frm, { overwrite: false });
    await apply_hdqt_opinion_visibility(frm);
    await apply_items6_opinion_scope(frm);
    await apply_items7_opinion_scope(frm);
    apply_items7_visibility(frm);
  },
  async scic_opinion(frm) {
    await sync_hdqt_member_tables(frm);
    // Toggle scic có thể tạo lại dòng bảng, nên fill deadline cha cho dòng chưa có deadline.
    sync_hdqt_deadline_from_parent(frm, { overwrite: false });
    await apply_items6_opinion_scope(frm);
    await apply_items7_opinion_scope(frm);
    apply_items7_visibility(frm);
    // Cập nhật mốc giá trị hợp lệ mới nhất để phục vụ rollback khi user không đủ quyền.
  },
  opinion_next(frm) {
    const docname = (frm.doc.name || "").trim();
    const isScicRound2 = is_checked(frm.doc.scic_opinion);
    const isHdqtSeries = docname.startsWith("VPHĐQT-");

    // Chỉ cho phép điều hướng khi đúng điều kiện nghiệp vụ:
    // 1) scic_opinion = 1
    // 2) mã phiếu bắt đầu bằng "VPHĐQT-"
    if (!isScicRound2 || !isHdqtSeries) {
      frappe.msgprint("Chỉ thực hiện được khi scic_opinion = 1 và mã phiếu bắt đầu bằng VPHĐQT-.");
      return;
    }

    // Tạo local draft bằng API chuẩn của Frappe rồi route thẳng vào form đó.
    const newDoc = frappe.model.get_new_doc("VNT Document Management");
    if (!newDoc) {
      frappe.msgprint("Không thể tạo phiếu mới. Vui lòng thử lại.");
      return;
    }

    // Copy các field header theo yêu cầu.
    newDoc.vnt_type = frm.doc.vnt_type || "";
    newDoc.lead_depart = frm.doc.lead_depart || "";
    newDoc.department = frm.doc.department || "";
    newDoc.document_date = frm.doc.document_date || '';
    newDoc.title = frm.doc.title || '';
    // Giữ nguyên cờ SCIC từ phiếu cũ (yêu cầu: scic_opinion = 1 lấy từ doc cũ).
    newDoc.scic_opinion = frm.doc.scic_opinion || 0;
    // Lưu liên kết về văn bản gốc để theo dõi chuỗi xin ý kiến.
    newDoc.link_doc = docname;

    // Copy bảng items6 theo yêu cầu: chỉ lấy Employee.
    // Dùng add_child để Frappe tự sinh cấu trúc row chuẩn (name/idx/doctype...).
    const sourceRows = Array.isArray(frm.doc.items6) ? frm.doc.items6 : [];
    sourceRows.forEach((src) => {
      const row = frappe.model.add_child(newDoc, "VNT Document Management Item6", "items6");
      row.employee = src.employee || "";
    });

    // Tránh route_options cũ ảnh hưởng dữ liệu của form mới.
    frappe.route_options = null;
    frappe.set_route("Form", "VNT Document Management", newDoc.name);
  },
  async enforce_items6_opinion_scope(frm) {
    await apply_items6_opinion_scope(frm);
  },
  async enforce_items7_opinion_scope(frm) {
    await apply_items7_opinion_scope(frm);
  },
  async refresh_vnt_type_filter(frm) {
    await apply_vnt_type_filter(frm);
  },
  // async hdqt_opinion (frm) {
  //   const shouldShow = await apply_hdqt_opinion_visibility(frm);
  //   if (!shouldShow || !is_checked(frm.doc.hdqt_opinion)) return;
  //   frappe.call({
  //       method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.employee_in_hdqt",
  //       args: {},
  //       callback: (r) => {
  //           if (r.message && r.message.length > 0) {
  //             const fields = [
  //               "thanh_vien_1",
  //               "thanh_vien_2",
  //               "thanh_vien_3",
  //               "thanh_vien_4",
  //               "thanh_vien_5",
  //               "thanh_vien_6",
  //               "thanh_vien_7"
  //             ];
  //             const updates = {};
  //             fields.forEach((fieldname, idx) => {
  //               updates[fieldname] = r.message[idx]?.name || null;
  //             });
  //             frm.set_value(updates);
  //           }
  //         }
  //     });
  // },
  async toggle_hdqt_opinion_visibility(frm) {
    await apply_hdqt_opinion_visibility(frm);
  },
  items6_add(frm) {
    // Dòng mới của items6 mặc định lấy deadline cha (nếu có), vẫn cho sửa tay.
    sync_hdqt_deadline_from_parent(frm, { overwrite: false });
    sync_summary_opinion(frm);
    frm.trigger("enforce_items6_opinion_scope");
    apply_items7_visibility(frm);
  },
  items6_remove(frm) {
    sync_summary_opinion(frm);
    frm.trigger("enforce_items6_opinion_scope");
    apply_items7_visibility(frm);
  },
  items7_add(frm) {
    // Dòng mới của items7 mặc định lấy deadline cha (nếu có), vẫn cho sửa tay.
    sync_hdqt_deadline_from_parent(frm, { overwrite: false });
    frm.trigger("enforce_items7_opinion_scope");
  },
  items7_remove(frm) {
    frm.trigger("enforce_items7_opinion_scope");
  },
  setup(frm) {
    patch_scroll_to_field(frm);
    frm.trigger("setup_cv_xu_ly_query");
    frm.trigger("setup_cv_xu_ly_query_items2");
  },

  validate(frm) {
    const late = find_late_item_deadline(frm);
    if (late) {
      frappe.throw(`Dòng ${late.idx}: Thời hạn hoàn thành ${late.typeLabel} không được muộn hơn thời hạn xử lý văn bản ${frm.doc.deadline}.`);
    }

    const multiChair = find_multiple_chair(frm);
    if (multiChair) {
      frappe.throw("Chỉ được phép chọn duy nhất 1 Người chủ trì trong bảng Người xử lý chính.");
    }

    if (frm.doc.handler_status && !has_any_role_row(frm)) {
      frappe.throw("Vui lòng chọn ít nhất 1 dòng Chủ trì/Phối hợp/Nhận để biết trước khi Chuyển xử lý.");
    }

    ensure_spec_deadline_not_after_chair(frm);
    if (frm.doc.vnt_type == "Công văn đi" &&  !frm.doc.document_date) {
      frm.set_value("document_date", frappe.datetime.now_date());
    }

    const update_history = (table_name) => {
      const rows = Array.isArray(frm.doc[table_name]) ? frm.doc[table_name] : [];
      let updated = false;
      rows.forEach((row) => {
        let changed = false;
        if (row.other && row.other.trim()) {
          const user = frappe.session.user_fullname || frappe.session.user || "Người dùng";
          const time = frappe.datetime.now_datetime();
          const new_msg = `${user} (${time}):\n${row.other}`;
          // Chỉ thêm vào history nếu new_msg chưa tồn tại để tránh duplicate khi Save nhiều lần
          if (!row.history || !row.history.includes(new_msg)) {
            row.history = row.history ? row.history + "\n---\n" + new_msg : new_msg;
            changed = true;
          }
        }
        if (row.explan && row.explan.trim()) {
          const user = frappe.session.user_fullname || frappe.session.user || "Người dùng";
          const now = frappe.datetime.now_datetime(); // "2026-03-13 10:30:45"
          const [date, time] = now.split(' ');
          const [year, month, day] = date.split('-');
          const dateFormatted = `${day}-${month}-${year}`; // "13-03-2026"
          const timeFormatted = time.substring(0, 5); // "10:30"
          const new_msg = `${user} (${dateFormatted} ${timeFormatted}):\n${row.explan}`;
          if (!row.history || !row.history.includes(new_msg)) {
            row.history = row.history ? row.history + "\n---\n" + new_msg : new_msg;
            changed = true;
          }
        }
        if (changed) updated = true;
      });
      if (updated) frm.refresh_field(table_name);
    };

    update_history("items6");
  },

  chairperson(frm) {
    if (frm.doc.chairperson) {
      frm.set_value("nguoi_chu_tri", frm.doc.chairperson);
    }
    frm.trigger("enforce_chair_edit_permission");
  },

  refresh(frm) {
    frm.set_df_property("items6", "cannot_add_rows", true);
    if (frm._handlerStatusLastSaved === undefined) {
      set_handler_status_prev(frm, frm.doc.handler_status || null);
    }
    if (frm._chairStatusLastSaved === undefined) {
      set_chair_status_prev(frm, frm.doc.chairperson_status || null);
    }
  
    // Luôn reset viewer mỗi lần refresh
    frm.trigger("render_attach");
    frm.trigger("sync_chair_from_items");
    frm.trigger("sync_collab_from_items");
    frm.trigger("render_process_flow");
    frm.trigger("enforce_handler_edit_permission");
    frm.trigger("enforce_creator_edit_permission");
    frm.trigger("enforce_chair_edit_permission");
    frm.trigger("setup_cv_xu_ly_query");
    frm.trigger("setup_cv_xu_ly_query_items2");
    frm.trigger("lock_items2_grid");
    // Đặt khóa sau cùng để ghi đè mọi toggle khác (không chờ async)
    enforce_chair_scope(frm);
    enforce_handler_scope(frm);
    enforce_specialist_scope(frm);
    enforce_collab_scope(frm);
    refresh_handler_controls_visibility(frm);
    toggle_process_section(frm);
    hide_legacy_fields(frm);
    frm.trigger("toggle_hdqt_opinion_visibility");
    sync_summary_opinion(frm);
    // frm.trigger("scic_opinion");
    frm.trigger("enforce_items6_opinion_scope");
    frm.trigger("enforce_items7_opinion_scope");
    frm.trigger("refresh_vnt_type_filter");

    if (has_full_document_access_role()) {
      apply_full_access_edit_override(frm);
    }
    // apply_items7_visibility(frm);

    // Chỉ set mặc định khi là phiếu mới
    if (frm.is_new()) {
      if (!frm.doc.employee) {
        frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name")
          .then(r => r?.message?.name && frm.set_value("employee", r.message.name));
      }
      if (!frm.doc.received_date) {
        frm.set_value("received_date", frappe.datetime.now_date());
      }
      if (frm.doc.vnt_type == "Công văn đi" && !frm.doc.document_date) {
        frm.set_value("document_date", frappe.datetime.now_date());
      }
      autofill_incoming_docu_number(frm);
      
      frm.trigger("prefill_level1_approvers");
    }
  },

  // Xử lý tất cả logic khi đổi loại văn bản (vnt_type)
  async vnt_type(frm) {
    const type = frm.doc.vnt_type || "";
    
    // === 1. Đặt naming_series theo loại văn bản ===
    if (type == "Công văn đến") {
      frm.set_value("naming_series", "CVĐEN.-.YY.-.####");
      await autofill_incoming_docu_number(frm);
    } else if (type == "Công văn đi") {
      // Tự động set ngày hiện tại nếu chưa có
      if (!frm.doc.document_date) {
        frm.set_value("document_date", frappe.datetime.now_date());
      }
      frm.set_value("naming_series", "CVĐI.-.YY.-.####");
      maybe_autofill_reference_number(frm);
    } else if (type == "Quyết định") {
      frm.set_value("naming_series", "QĐ.-.YY.-.####");
      // Autofill reference_number: 01/QĐ-TĐDMVN, 02/QĐ-TĐDMVN, ...
      await autofill_qd_reference_number(frm);
    } else if (type == "Nội bộ ban") {
      // Dạng naming_series động: {short_name_depart}.-.YY.-.####
      // VD: "HR.-.26.-.0001" (HR là viết tắt phòng ban, 26 là năm, 0001 là số thứ tự)
      frm.set_value("naming_series", "{short_name_depart}.-.YY.-.####");
      
      // Tự động điền lead_depart = employee hiện tại nếu là "Nội bộ ban"
      if (is_noi_bo_ban_type(type)) {
        const currentEmp = await get_current_employee(frm);
        if (currentEmp && (frm.doc.lead_depart || "").trim() !== currentEmp) {
          await frm.set_value("lead_depart", currentEmp);
        }
      }
    }

    // === 2. Áp dụng các quy tắc chỉnh sửa quyền hạn & UI ===
    frm.trigger("enforce_handler_edit_permission");
    frm.trigger("enforce_creator_edit_permission");
    frm.trigger("enforce_chair_edit_permission");
    toggle_process_section(frm);
    
    // === 3. Điền sẵn Level 1 Approver cho "Công văn đến" ===
    if (type.trim() === "Công văn đến") {
      frm.trigger("prefill_level1_approvers");
    }
  },

  department(frm) {
    maybe_autofill_reference_number(frm, { force: true });
  },
  type_doc(frm) {
    maybe_autofill_reference_number(frm, { force: true});
    
  },

  deadline(frm) {
    const val = frm.doc.deadline || null;
    if (frm.doc.deadline_copy !== val) {
      frm.set_value("deadline_copy", val);
    }
    // Khi user chọn lại deadline cha, đồng bộ lại toàn bộ deadline items6/items7 theo giá trị mới.
    sync_hdqt_deadline_from_parent(frm, { overwrite: true });
  },

  document_date(frm) {
    // Autofill reference_number khi người dùng thay đổi ngày
    // - Công văn đi: gọi maybe_autofill_reference_number
    // - Quyết định: gọi autofill_qd_reference_number (reset số mỗi khi sang năm mới)
    maybe_autofill_reference_number(frm, { force: true });
    autofill_qd_reference_number(frm, { force: true });
  },

  // Khi trường attach đổi, render lại
  attach(frm) {
    frm.trigger("render_attach");
  },

  // Render sơ đồ luồng xử lý
  employee(frm) {
    frm.trigger("render_process_flow");
  },

  handler(frm) {
    frm.trigger("render_process_flow");
    frm.trigger("enforce_handler_edit_permission");
    frm.trigger("enforce_creator_edit_permission");
    frm.trigger("enforce_chair_edit_permission");
    refresh_handler_controls_visibility(frm);
  },

  employee_status(frm) {
    frm.trigger("render_process_flow");
  },

  async handler_status(frm) {
    if ((frm.doc.vnt_type || "").trim() === "Công văn đến") {
      const currentEmp = await get_current_employee(frm);
      const isInternal = is_checked(frm.doc.internal);
      const handlerOwner = get_handler_owner(frm);
      if (handlerOwner) {
        const isAllowed = currentEmp && handlerOwner === currentEmp;
        if (!isAllowed) {
          frappe.msgprint(isInternal
            ? "Chỉ Lãnh đạo Ban được chỉ định mới có thể Chuyển xử lý."
            : "Chỉ Lãnh đạo Tập đoàn được chỉ định mới có thể Chuyển xử lý.");
          return;
        }
      }
    }

    if (frm._handlerStatusSaving) return;
    if (is_checked(frm.doc.is_handler_status)) {
      frappe.msgprint("Văn bản đã được chuyển xử lý trước đó, không gửi lại thông báo.");
      return;
    }

    const check = validate_handler_status_preconditions(frm);
    if (!check.ok) {
      frappe.msgprint(check.message);
      return;
    }

    if (!frm.doc.handler_transferred_at) {
      const now = frappe.datetime.now_datetime();
      if (frm.get_field("handler_transferred_at")) {
        await frm.set_value("handler_transferred_at", now);
      } else {
        frm.doc.handler_transferred_at = now;
      }
    }

    const isInternal = is_checked(frm.doc.internal);
    const removed = prune_items_without_role(frm, isInternal ? ["items4"] : ["items"]);
    if (removed) {
      frm.trigger("sync_chair_from_items");
      frm.trigger("sync_collab_from_items");
    }

    // Đảm bảo có name trước khi gọi server
    const needsSave = !frm.doc.name || frm.is_dirty() || removed;
    if (needsSave) {
      await frm.save();
      if (frm.is_dirty()) {
        return;
      }
    }

    frm._handlerStatusSaving = true;
    try {
      await frappe.call({
        method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.trigger_handler_transfer",
        args: { docname: frm.doc.name }
      });
      await frm.reload_doc();
      set_handler_status_prev(frm, frm.doc.handler_status || null);
      frm.trigger("render_process_flow");
      if (!is_checked(frm.doc.is_handler_status)) {
        await frm.set_value("is_handler_status", 1);
        await frm.save();
      }
    } catch (err) {
      frappe.msgprint("Thao tác Chuyển văn bản không thành công. Vui lòng thử lại.");
      // eslint-disable-next-line no-console
      console.error(err);
    }
    frm._handlerStatusSaving = false;
  },

  chairperson(frm) {
    frm.trigger("render_process_flow");
  },

  deadline_cv_xu_ly(frm) {
    ensure_spec_deadline_not_after_chair(frm);
  },

  chairperson_status(frm) {
    if (frm._chairStatusSaving) return;
    if (frm._chairStatusResetting) return;

    const prev = get_chair_status_prev(frm);
    if (is_done(frm.doc.chairperson_status) && !all_specialists_done(frm)) {
      frappe.msgprint("Người chủ trì chỉ được chọn Hoàn thành sau khi Chuyên viên và tất cả Người phối hợp đã Hoàn thành.");
      frm._chairStatusResetting = true;
      frm.set_value("chairperson_status", prev);
      frm._chairStatusResetting = false;
      return;
    }

    if (is_done(frm.doc.chairperson_status) && !is_done(prev)) {
      if (frm.get_field("chairperson_completed_at")) {
        frm.set_value("chairperson_completed_at", frappe.datetime.now_datetime());
      } else {
        frm.doc.chairperson_completed_at = frappe.datetime.now_datetime();
      }
    } else if (!is_done(frm.doc.chairperson_status) && frm.doc.chairperson_completed_at) {
      if (frm.get_field("chairperson_completed_at")) {
        frm.set_value("chairperson_completed_at", null);
      } else {
        frm.doc.chairperson_completed_at = null;
      }
    }

    set_chair_status_prev(frm, frm.doc.chairperson_status || null);
    frm.trigger("render_process_flow");
  },

  collaborator(frm) {
    frm.trigger("render_process_flow");
  },

  collaborator_status(frm) {
    frm.trigger("render_process_flow");
  },

  cv_xu_ly(frm) {
    if (frm.doc.cv_xu_ly && !frm.doc.cv_xu_ly_assigned_at) {
      const now = frappe.datetime.now_datetime();
      if (frm.get_field("cv_xu_ly_assigned_at")) {
        frm.set_value("cv_xu_ly_assigned_at", now);
      } else {
        frm.doc.cv_xu_ly_assigned_at = now;
      }
    } else if (!frm.doc.cv_xu_ly && frm.doc.cv_xu_ly_assigned_at) {
      if (frm.get_field("cv_xu_ly_assigned_at")) {
        frm.set_value("cv_xu_ly_assigned_at", null);
      } else {
        frm.doc.cv_xu_ly_assigned_at = null;
      }
    }
    frm.trigger("render_process_flow");
    frm.trigger("enforce_chair_edit_permission");
    enforce_specialist_scope(frm);
    enforce_collab_scope(frm);
  },

  trang_thai_chuyen_vien_xu_ly(frm) {
    if (is_done(frm.doc.trang_thai_chuyen_vien_xu_ly) && !frm.doc.cv_xu_ly_completed_at) {
      if (frm.get_field("cv_xu_ly_completed_at")) {
        frm.set_value("cv_xu_ly_completed_at", frappe.datetime.now_datetime());
      } else {
        frm.doc.cv_xu_ly_completed_at = frappe.datetime.now_datetime();
      }
    } else if (!is_done(frm.doc.trang_thai_chuyen_vien_xu_ly) && frm.doc.cv_xu_ly_completed_at) {
      if (frm.get_field("cv_xu_ly_completed_at")) {
        frm.set_value("cv_xu_ly_completed_at", null);
      } else {
        frm.doc.cv_xu_ly_completed_at = null;
      }
    }
    frm.trigger("render_process_flow");
  },

  info_recipient(frm) {
    frm.trigger("render_process_flow");
  },

  info_recipient_status(frm) {
    frm.trigger("render_process_flow");
  },

  async enforce_handler_edit_permission(frm) {
    await apply_handler_edit_lock(frm);
  },

  async enforce_creator_edit_permission(frm) {
    await apply_creator_edit_lock(frm);
  },

  async enforce_chair_edit_permission(frm) {
    await apply_chair_edit_lock(frm);
  },

  setup_cv_xu_ly_query(frm) {
    frm.set_query("cv_xu_ly", () => {
      const department = get_chair_department(frm);
      if (!department) {
        if (!frm._cvXuLyMissingDeptWarned) {
          frappe.msgprint("Vui lòng chọn Người chủ trì (có phòng/ban) trước khi chọn Chuyên viên xử lý.");
          frm._cvXuLyMissingDeptWarned = true;
        }
        // Trả về filter vô hiệu để tránh chọn sai khi chưa có phòng/ban
        return { filters: { name: "__no_chair_department__" } };
      }
      frm._cvXuLyMissingDeptWarned = false;
      return { filters: { department } };
    });
  },

  setup_cv_xu_ly_query_items2(frm) {
    frm.set_query("cv_xu_ly", "items2", (_frm, cdt, cdn) => {
      const row = (locals[cdt] && locals[cdt][cdn]) || {};
      if (!row.nguoi_phoi_hop) {
        if (!frm._cvXuLyMissingCollabWarned) {
          frappe.msgprint("Vui lòng chọn Người phối hợp trước khi chọn Chuyên viên xử lý.");
          frm._cvXuLyMissingCollabWarned = true;
        }
        return { filters: { name: "__no_collaborator__" } };
      }
      frm._cvXuLyMissingCollabWarned = false;
      return {
        query: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.filter_cv_xu_ly_by_collab",
        filters: { nguoi_phoi_hop: row.nguoi_phoi_hop }
      };
    });
  },

  lock_items2_grid(frm) {
    if (has_full_document_access_role()) {
      const grid = frm.fields_dict.items2?.grid;
      if (!grid) return;
      grid.cannot_add_rows = false;
      grid.cannot_delete_rows = false;
      grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").show();
      grid.refresh();
      return;
    }

    const grid = frm.fields_dict.items2?.grid;
    if (!grid) return;
    grid.cannot_add_rows = true;
    grid.cannot_delete_rows = true;
    grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
  },

  sync_chair_from_items(frm) {
    const rows = get_role_rows(frm);
    const picked = rows.find(r => r.chu_tri);
    const updates = {};

    if (!picked) {
      if (frm.doc.nguoi_chu_tri) updates.nguoi_chu_tri = null;
      if (frm.doc.deadline_chu_tri2) updates.deadline_chu_tri2 = null;
      if (frm.doc.chairperson_status) updates.chairperson_status = null;
    } else {
      if (picked.employee && frm.doc.nguoi_chu_tri !== picked.employee) {
        updates.nguoi_chu_tri = picked.employee;
      }
      if (picked.deadline && frm.doc.deadline_chu_tri2 !== picked.deadline) {
        updates.deadline_chu_tri2 = picked.deadline;
      }
      if (!frm.doc.chairperson_status) {
        updates.chairperson_status = "Đang xử lý";
      }
    }

    if (Object.keys(updates).length) frm.set_value(updates);
    frm.trigger("enforce_chair_edit_permission");
  },

  sync_collab_from_items(frm) {
    const srcRows = get_role_rows(frm).filter(r => r.phoi_hop);
    const tgtRows = Array.isArray(frm.doc.items2) ? frm.doc.items2 : [];

    const srcByEmp = new Map();
    srcRows.forEach(r => {
      if (r.employee) srcByEmp.set(r.employee, r);
    });

    const toRemove = [];
    tgtRows.forEach((row, idx) => {
      if (!row.nguoi_phoi_hop) return;
      if (!srcByEmp.has(row.nguoi_phoi_hop)) {
        toRemove.push(idx);
        return;
      }

      const src = srcByEmp.get(row.nguoi_phoi_hop);
      if (!row.trang_thai_nguoi_phoi_hop) {
        row.trang_thai_nguoi_phoi_hop = "Đang xử lý";
      }
      if (src?.deadline && row.deadline1 !== src.deadline) {
        row.deadline1 = src.deadline;
      }
    });

    const existing = new Set(tgtRows.map(r => r.nguoi_phoi_hop).filter(Boolean));
    srcByEmp.forEach((r, emp) => {
      if (existing.has(emp)) return;
      const child = frm.add_child("items2");
      child.nguoi_phoi_hop = emp;
      if (r.deadline) child.deadline1 = r.deadline;
      child.trang_thai_nguoi_phoi_hop = "Đang xử lý";
    });

    // remove from end to keep indexes valid
    toRemove.sort((a, b) => b - a).forEach((idx) => frm.doc.items2.splice(idx, 1));

    if (srcRows.length || toRemove.length) {
      frm.refresh_field("items2");
    }
  },

  prefill_level1_approvers(frm) {
    if (!frm.is_new()) return;
    const docType = (frm.doc.vnt_type || "").trim();
    if (docType !== "Công văn đến") return;

    const hasCapCao = Array.isArray(frm.doc.item2) && frm.doc.item2.length;
    const hasCapTrung = Array.isArray(frm.doc.items) && frm.doc.items.length;
    if (hasCapCao && hasCapTrung) return;

    frappe.call({
      method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.get_company_leadership",
      args: { company: frm.doc.company || null },
      freeze: false,
      callback: (r) => {
        const payload = r?.message || {};
        const rowsCapCao = Array.isArray(payload.cap_cao) ? payload.cap_cao : [];
        const rowsCapTrung = Array.isArray(payload.cap_trung) ? payload.cap_trung : [];

        const hasCapCaoNow = Array.isArray(frm.doc.item2) && frm.doc.item2.length;
        const hasCapTrungNow = Array.isArray(frm.doc.items) && frm.doc.items.length;

        if (frm.get_field("item2") && !hasCapCaoNow && rowsCapCao.length) {
          frm.clear_table("item2");
          rowsCapCao.forEach((item) => {
            const row = frm.add_child("item2");
            row.employee = item.employee;
            row.department = item.department;
            row.deadline = item.deadline;
            row.chu_tri = item.chu_tri;
            row.phoi_hop = item.phoi_hop;
            row.nhan_de_biet = item.nhan_de_biet;
          });
          frm.refresh_field("item2");
        }

        if (frm.get_field("items") && !hasCapTrungNow && rowsCapTrung.length) {
          frm.clear_table("items");
          rowsCapTrung.forEach((item) => {
            const row = frm.add_child("items");
            row.employee = item.employee;
            row.department = item.department;
            row.deadline = item.deadline;
            row.chu_tri = item.chu_tri;
            row.phoi_hop = item.phoi_hop;
            row.nhan_de_biet = item.nhan_de_biet;
          });
          frm.refresh_field("items");
        }
      }
    });
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
  },

  render_process_flow(frm) {
    const $wrap = frm.fields_dict.html_editer?.$wrapper;
    if (!$wrap) return;

    const grid = frm.fields_dict.items?.grid;
    if (grid && !grid._vnt_flow_bound) {
      grid.wrapper.on("data-change", () => {
        frm.trigger("sync_chair_from_items");
        frm.trigger("sync_collab_from_items");
        frm.trigger("render_process_flow");
      });
      grid._vnt_flow_bound = true;
    }

    const gridItem2 = frm.fields_dict.item2?.grid;
    if (gridItem2 && !gridItem2._vnt_flow_bound) {
      gridItem2.wrapper.on("data-change", () => {
        frm.trigger("sync_chair_from_items");
        frm.trigger("sync_collab_from_items");
        frm.trigger("render_process_flow");
      });
      gridItem2._vnt_flow_bound = true;
    }

    const gridItems4 = frm.fields_dict.items4?.grid;
    if (gridItems4 && !gridItems4._vnt_flow_bound) {
      gridItems4.wrapper.on("data-change", () => {
        frm.trigger("sync_chair_from_items");
        frm.trigger("sync_collab_from_items");
        frm.trigger("render_process_flow");
      });
      gridItems4._vnt_flow_bound = true;
    }

    const grid2 = frm.fields_dict.items2?.grid;
    if (grid2 && !grid2._vnt_flow_bound) {
      grid2.wrapper.on("data-change", () => {
        frm.trigger("sync_chair_from_items");
        frm.trigger("sync_collab_from_items");
        frm.trigger("render_process_flow");
      });
      grid2._vnt_flow_bound = true;
    }

    // Chuẩn bị cache tên đầy đủ Employee
    frm._empNameCache = frm._empNameCache || {};
    const nameCache = frm._empNameCache;
    const ids = new Set();
    const addId = (val) => {
      if (val) ids.add(val);
    };

    addId(frm.doc.employee);
    addId(frm.doc.handler);
    addId(frm.doc.lead_depart);
    addId(frm.doc.chairperson);
    addId(frm.doc.cv_xu_ly);
    const rowsMain = get_role_rows(frm);
    const rowsCollab = Array.isArray(frm.doc.items2) ? frm.doc.items2 : [];
    rowsMain.forEach((r) => {
      addId(r.employee || r.employee_id);
      addId(r.chairperson);
      addId(r.nhan_de_biet);
    });
    rowsCollab.forEach((r) => {
      addId(r.employee);
      addId(r.nguoi_phoi_hop);
      addId(r.cv_xu_ly);
    });

    const missing = [...ids].filter((id) => id && !nameCache[id]);
    if (missing.length && !frm._empNameLoading) {
      frm._empNameLoading = true;
      frappe.call({
        method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.get_employee_display_names",
        args: { employee_ids: missing },
        callback: (r) => {
          const mapping = r?.message || {};
          missing.forEach((id) => {
            nameCache[id] = mapping[id] || id;
          });
          frm._empNameLoading = false;
          frm._empNameCache = nameCache;
          frm.trigger("render_process_flow");
        }
      });
      return;
    }
    if (frm._empNameLoading) return;

    const displayEmployee = (id) => {
      if (!id) return "Chưa chọn";
      return frappe.utils.escape_html(nameCache[id] || id);
    };
    const formatTimeValue = (val) => {
      if (!val) return "";
      try {
        const formatted = frappe.datetime.str_to_user(val);
        return formatted.replace(/(\d{1,2}:\d{2}):\d{2}/, "$1");
      } catch (err) {
        return val;
      }
    };

    const SCALE = 0.85;
    const stackSpacing = 150;
    const baseSize = { width: 1300, height: 700 };

    const noPlaceholderKeys = new Set(["employee_status", "handler_status"]);
    const statusLabel = (key) => {
      const raw = (frm.doc[key] || "").trim();
      if (!raw && noPlaceholderKeys.has(key)) return "";
      return raw || "Chưa có trạng thái";
    };

    const statusColor = (key) => {
      const status = (frm.doc[key] || "").trim();
      if (!status) return "#94a3b8";
      if (status === "Hoàn thành") return "#22c55e";
      if (status === "Trả lại") return "#f59e0b";
      if (status === "Đang xử lý") return "#3b82f6";
      return "#e85b5b";
    };

    const statusInfo = (key) => ({
      label: statusLabel(key),
      color: statusColor(key)
    });
    const is_handler_transferred = (val) => (val || "").trim() === "Chuyển văn bản";
    const statusColorValue = (val) => {
      const status = (val || "").trim();
      if (!status) return "#94a3b8";
      if (status === "Hoàn thành") return "#22c55e";
      if (status === "Trả lại") return "#f59e0b";
      if (status === "Đang xử lý") return "#3b82f6";
      return "#e85b5b";
    };

    const fillByStroke = (color) => {
      if (color === "#22c55e") return "#e8f8f0"; // green
      if (color === "#f59e0b") return "#fef3c7"; // yellow
      if (color === "#3b82f6") return "#e0ecff"; // blue
      if (color === "#e85b5b") return "#fee2e2"; // red
      if (color === "#94a3b8") return "#e5e7eb"; // grey/empty
      if (color === "#f9a8d4") return "#fce7f3"; // pink
      return "#f8fafc";
    };

    const today = frappe.datetime.get_today();
    const isOverdue = (deadline, statusVal) => {
      if (!deadline) return false;
      if ((statusVal || "").trim() === "Hoàn thành") return false;
      return deadline < today;
    };
    const parse_datetime_value = (val) => {
      if (!val) return null;
      if (val instanceof Date) return val;
      try {
        return frappe.datetime.str_to_obj(val);
      } catch (err) {
        return null;
      }
    };
    const is_late_completion = (deadline, completedAt) => {
      const deadlineVal = parse_datetime_value(deadline);
      const completedVal = parse_datetime_value(completedAt);
      if (!deadlineVal || !completedVal) return false;
      return completedVal > deadlineVal;
    };

    const colorForNode = (node) => {
      // Văn thư luôn xanh hoàn thành
      if (node.key === "employee") return "#22c55e";

      if (node.deadlineAt && node.completedAt && is_late_completion(node.deadlineAt, node.completedAt)) {
        return "#e85b5b";
      }

      if (node.statusKey) {
        const currentStatus = (frm.doc[node.statusKey] || "").trim();
        // Lãnh đạo tập đoàn: xanh khi trạng thái "Chuyển văn bản"
        if (node.key === "handler") {
          return "#22c55e";
        }
        
        return statusColor(node.statusKey);
      }

      return node.stroke || "#3b82f6";
    };

    const roleNodes = [];

    const addRoleNodes = (rows, roleKey, label, flagField, x, startY, opts = {}) => {
      let count = 0;
      rows.forEach((row, idx) => {
        if (!row[flagField]) return;
        const value = displayEmployee(row.employee || row.employee_name || row.employee_id || row.nguoi_phoi_hop || "");
        const color = opts.colorForRow ? opts.colorForRow(row) : roleKey === "info_recipient" ? "#111827" : "#22c55e";
        const showStatus = opts.showStatus ?? false;
        const statusText = opts.statusText ? opts.statusText(row) : "";
        const statusValue = typeof opts.statusValue === "function" ? opts.statusValue(row) : opts.statusValue;
        const receivedAt = typeof opts.receivedAt === "function" ? opts.receivedAt(row) : row.creation;
        const completedAt = typeof opts.completedAt === "function"
          ? opts.completedAt(row, statusValue)
          : (is_done(statusValue) ? row.modified : "");
        const deadlineAt = typeof opts.deadlineAt === "function" ? opts.deadlineAt(row) : opts.deadlineAt;
        const extra = typeof opts.extraForRow === "function" ? opts.extraForRow(row, idx) : null;
        roleNodes.push({
          key: `${roleKey}-${idx}`,
          label,
          value,
          stroke: color,
          statusLabel: statusText,
          showStatus,
          receivedAt,
          completedAt,
          deadlineAt,
          hideCompletedTime: opts.hideCompletedTime,
          hideTimes: extra?.hideTimes,
          extraLines: extra?.extraLines || null,
          x,
          y: startY + count * stackSpacing
        });
        count += 1;
      });
      return count;
    };

    const docCreatedAt = frm.doc.creation || "";
    const docReceivedAt = frm.doc.received_date || docCreatedAt || "";
    const employeeCompletedAt = docCreatedAt;
    const handlerCompletedAt = frm.doc.handler_transferred_at || "";
    const isInternal = is_checked(frm.doc.internal);
    const handlerLabel = isInternal ? "Lãnh đạo Ban" : "Lãnh Đạo Tập Đoàn";
    const handlerDisplayId = (isInternal && frm.doc.lead_depart) ? frm.doc.lead_depart : frm.doc.handler;

    const chairStart = 40;
    const chairX = 650;
    const specialistX = 1000;
    const chairColor = statusColorValue(frm.doc.chairperson_status);
    const chairCount = addRoleNodes(
      rowsMain,
      "chairperson",
      "Người chủ trì",
      "chu_tri",
      chairX,
      chairStart,
      {
        colorForRow: (row) => {
          const overdue = isOverdue(frm.doc.deadline_chu_tri2, frm.doc.chairperson_status);
          if (overdue) return "#e85b5b";
          return chairColor;
        },
        statusValue: () => frm.doc.chairperson_status,
        receivedAt: () => handlerCompletedAt || "",
        completedAt: (_row, statusValue) => {
          if (!is_done(statusValue)) return "";
          return frm.doc.chairperson_completed_at || frm.doc.modified || "";
        },
        deadlineAt: () => frm.doc.deadline_chu_tri2 || "",
        showStatus: true,
        statusText: (row) => {
          const overdue = isOverdue(frm.doc.deadline_chu_tri2, frm.doc.chairperson_status);
          if (overdue) return "Quá hạn";
          return frm.doc.chairperson_status || "";
        }
      }
    );

    const collabStart = chairStart + Math.max(chairCount, 1) * stackSpacing + 30;
    const collabCount = addRoleNodes(
      rowsCollab,
      "collaborator",
      "Người phối hợp",
      "nguoi_phoi_hop",
      chairX,
      collabStart,
      {
        colorForRow: (row) => {
          const overdue = isOverdue(row.deadline1, row.trang_thai_nguoi_phoi_hop || row.trang_thai_cv_xu_ly);
          if (overdue) return "#e85b5b";
          return statusColorValue(row.trang_thai_nguoi_phoi_hop || row.trang_thai_cv_xu_ly);
        },
        statusValue: (row) => row.trang_thai_nguoi_phoi_hop,
        receivedAt: () => handlerCompletedAt || "",
        completedAt: (row, statusValue) => {
          if (!is_done(statusValue)) return "";
          return row.nguoi_phoi_hop_completed_at || row.modified || "";
        },
        deadlineAt: (row) => row.deadline1 || "",
        showStatus: true,
        statusText: (row) => {
          const overdue = isOverdue(row.deadline1, row.trang_thai_nguoi_phoi_hop || row.trang_thai_cv_xu_ly);
          if (overdue) return "Quá hạn";
          return row.trang_thai_nguoi_phoi_hop || "";
        }
      }
    );

    const infoStart = collabStart + Math.max(collabCount, 1) * stackSpacing + 30;
    const infoCount = addRoleNodes(
      rowsMain,
      "info_recipient",
      "Nhận để biết",
      "nhan_de_biet",
      chairX,
      infoStart,
      {
        colorForRow: (row) => (row.nhan_de_biet ? "#22c55e" : "#111827"),
        hideCompletedTime: true,
        receivedAt: () => handlerCompletedAt || "",
        completedAt: () => ""
      }
    );

    const lastStackEnd = infoStart + Math.max(infoCount, 1) * stackSpacing;
    // Giảm khoảng trống đáy để không dư quá nhiều
    baseSize.height = Math.max(420, lastStackEnd + 60);

    const nodeSize = { width: 200, height: 112 };

    const nodes = [
      {
        key: "employee",
        label: "Văn thư",
        value: displayEmployee(frm.doc.employee),
        stroke: "#3b82f6",
        fill: "#e0ecff",
        statusKey: "employee_status",
        receivedAt: docReceivedAt,
        completedAt: employeeCompletedAt,
        completedLabel: "Chuyển",
        x: 18,
        y: 108
      },
      {
        key: "handler",
        label: handlerLabel,
        value: displayEmployee(handlerDisplayId),
        stroke: "#f59e0b",
        fill: "#fef3c7",
        statusKey: "handler_status",
        showStatus: false,
        receivedAt: employeeCompletedAt,
        completedAt: handlerCompletedAt,
        completedLabel: "Giao",
        x: 320,
        y: 108
      }
    ];

    const hasPrimarySpecialist = chairCount > 0 && (frm.doc.cv_xu_ly || "").trim();
    if (hasPrimarySpecialist) {
      const primaryOverdue = isOverdue(frm.doc.deadline_cv_xu_ly, frm.doc.trang_thai_chuyen_vien_xu_ly);
      const primaryCompletedAt = is_done(frm.doc.trang_thai_chuyen_vien_xu_ly)
        ? (frm.doc.cv_xu_ly_completed_at || frm.doc.modified || "")
        : "";
      const primaryLate = is_late_completion(frm.doc.deadline_cv_xu_ly, primaryCompletedAt);
      nodes.push({
        key: "specialist_primary",
        label: "Chuyên viên xử lý",
        value: displayEmployee(frm.doc.cv_xu_ly),
        stroke: (primaryOverdue || primaryLate) ? "#e85b5b" : statusColorValue(frm.doc.trang_thai_chuyen_vien_xu_ly || ""),
        fill: primaryOverdue
          ? fillByStroke("#e85b5b")
          : fillByStroke(statusColorValue(frm.doc.trang_thai_chuyen_vien_xu_ly || "")),
        statusKey: "trang_thai_chuyen_vien_xu_ly",
        receivedAt: frm.doc.cv_xu_ly_assigned_at || (frm.doc.cv_xu_ly ? frm.doc.modified : ""),
        completedAt: primaryCompletedAt,
        deadlineAt: frm.doc.deadline_cv_xu_ly || "",
        x: specialistX,
        y: chairStart + ((chairCount - 1) * stackSpacing) / 2
      });
    }

    rowsCollab.forEach((row, idx) => {
      if (!row.nguoi_phoi_hop || !row.cv_xu_ly) return;
      const baseY = collabStart + idx * stackSpacing;
      const specKey = `specialist_collab-${idx}`;
      const overdue = isOverdue(row.deadline2, row.trang_thai_cv_xu_ly);
      const stroke = overdue ? "#e85b5b" : statusColorValue(row.trang_thai_cv_xu_ly);
      const completedAt = is_done(row.trang_thai_cv_xu_ly)
        ? (row.cv_xu_ly_completed_at || row.modified || "")
        : "";
      const late = is_late_completion(row.deadline2, completedAt);
      nodes.push({
        key: specKey,
        label: "Chuyên viên xử lý",
        value: displayEmployee(row.cv_xu_ly),
        stroke: late ? "#e85b5b" : stroke,
        fill: fillByStroke(stroke),
        statusKey: null,
        statusLabel: overdue ? "Quá hạn" : row.trang_thai_cv_xu_ly || "",
        showStatus: true,
        receivedAt: row.cv_xu_ly_assigned_at || (row.cv_xu_ly ? row.modified : ""),
        completedAt,
        deadlineAt: row.deadline2 || "",
        x: specialistX,
        y: baseY
      });
    });

    
    nodes.push(...roleNodes);
    let incomingDocKey = null;
    const isIncoming = (frm.doc.vnt_type || "").trim() === "Công văn đến";
    const outgoingDocValue = (frm.doc.cong_van_di || "").trim();
    if (isIncoming && outgoingDocValue) {
      const employeeNode = nodes.find((node) => node.key === "employee") || null;
      if (employeeNode) {
        nodes.push({
          key: "incoming_doc",
          label: "Công văn đi tương ứng",
          value: frappe.utils.escape_html(outgoingDocValue),
          stroke: "#f9a8d4",
          fill: fillByStroke("#f9a8d4"),
          hideTimes: true,
          x: employeeNode.x,
          y: employeeNode.y + nodeSize.height + 60
        });
        incomingDocKey = "incoming_doc";
      }
    }

    // Tính chiều rộng bám sát nút xa nhất để tránh vùng trống dư
    const maxNodeRight = nodes.reduce((max, n) => Math.max(max, n.x + nodeSize.width), 0);
    const maxNodeBottom = nodes.reduce((max, n) => Math.max(max, n.y + nodeSize.height), 0);
    baseSize.width = Math.max(maxNodeRight + 80, 480);
    baseSize.height = Math.max(baseSize.height, maxNodeBottom + 60);
    const scaledSize = {
      width: Math.round(baseSize.width * SCALE),
      height: Math.round(baseSize.height * SCALE)
    };

    const nodeByKey = Object.fromEntries(nodes.map((n) => [n.key, n]));
    const anchorRight = (node) => ({
      x: node.x + nodeSize.width,
      y: node.y + nodeSize.height / 2
    });
    const anchorLeft = (node) => ({
      x: node.x,
      y: node.y + nodeSize.height / 2
    });

    const connections = [
      { from: "employee", to: "handler", color: "#22c55e", dashed: false }
    ];
    if (incomingDocKey) {
      connections.push({ from: "employee", to: incomingDocKey, color: "#f9a8d4", dashed: false });
    }
    roleNodes.forEach((node) => {
      const isInfo = node.key.startsWith("info_recipient");
      const isCollab = node.key.startsWith("collaborator");
      connections.push({
        from: "handler",
        to: node.key,
        color: colorForNode(node),
        dashed: isInfo || isCollab
      });

      if (node.key.startsWith("chairperson")) {
        if (nodeByKey["specialist_primary"]) {
          const primaryNode = nodeByKey["specialist_primary"];
          const primaryLate = is_late_completion(primaryNode.deadlineAt, primaryNode.completedAt);
          connections.push({
            from: node.key,
            to: "specialist_primary",
            statusKey: primaryLate ? null : "trang_thai_chuyen_vien_xu_ly",
            color: primaryLate ? "#e85b5b" : undefined,
            dashed: false
          });
        }
      }
      if (node.key.startsWith("collaborator")) {
        const idx = node.key.split("-")[1];
        const specKey = `specialist_collab-${idx}`;
        const targetExists = nodes.find((n) => n.key === specKey);
        if (targetExists) {
          const row = rowsCollab[idx] || {};
          const completedAt = is_done(row.trang_thai_cv_xu_ly) ? row.modified : "";
          const late = is_late_completion(row.deadline2, completedAt);
          connections.push({
            from: node.key,
            to: specKey,
            statusKey: null,
            color: late ? "#e85b5b" : statusColorValue(rowsCollab[idx]?.trang_thai_cv_xu_ly),
            dashed: false
          });
        }
      }
    });

    const colorForConn = (conn) => conn.color || statusColor(conn.statusKey);
    const uniqueColors = [...new Set(connections.map(colorForConn))];
    const arrowDefs = uniqueColors
      .map(
        (color) => `
        <marker id="vnt-arrow-${color.slice(1)}" markerWidth="10" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L10,4 L0,8 z" fill="${color}" />
        </marker>`
      )
      .join("");

    const linePath = (conn) => {
      const startNode = nodeByKey[conn.from];
      const endNode = nodeByKey[conn.to];
      if (!startNode || !endNode) return "";

      const start = anchorRight(startNode);
      const end = anchorLeft(endNode);
      const midX = (start.x + end.x) / 2;
      const path = `M ${start.x} ${start.y} L ${midX} ${start.y} L ${midX} ${end.y} L ${end.x} ${end.y}`;

      const color = colorForConn(conn);
      const arrowId = `vnt-arrow-${color.slice(1)}`;
      const dash = conn.dashed ? 'stroke-dasharray="7 5"' : "";
      return `<path d="${path}" fill="none" stroke="${color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" ${dash} marker-end="url(#${arrowId})"></path>`;
    };

    const nodeTemplate = (node) => {
      const stroke = colorForNode(node);
      const fill = fillByStroke(stroke);
      const receivedText = `Nhận: ${formatTimeValue(node.receivedAt) || "-"}`;
      const completedLabel = node.completedLabel || "Hoàn thành";
      const completedText = `${completedLabel}: ${formatTimeValue(node.completedAt) || "-"}`;
      const showDeadline = node.deadlineAt !== undefined;
      const showCompleted = !node.hideCompletedTime;
      const deadlineText = showDeadline
        ? `Deadline: ${formatTimeValue(node.deadlineAt) || "-"}`
        : "";
      const completedY = showDeadline ? node.y + 94 : node.y + 78;
      const timeLines = node.hideTimes
        ? ""
        : `
          <text x="${node.x + 12}" y="${node.y + 62}" class="vnt-node-time">${receivedText}</text>
          ${showDeadline ? `<text x="${node.x + 12}" y="${node.y + 78}" class="vnt-node-time">${deadlineText}</text>` : ""}
          ${showCompleted ? `<text x="${node.x + 12}" y="${completedY}" class="vnt-node-time">${completedText}</text>` : ""}
        `;
      const extraLines = Array.isArray(node.extraLines) && node.extraLines.length && node.hideTimes
        ? node.extraLines.map((line, idx) => {
          const safeLine = frappe.utils.escape_html(line || "");
          const y = node.y + 62 + idx * 16;
          return `<text x="${node.x + 12}" y="${y}" class="vnt-node-extra">${safeLine}</text>`;
        }).join("")
        : "";

      return `
        <g class="vnt-node" data-role="${node.key}">
          <rect x="${node.x}" y="${node.y}" rx="10" ry="10" width="${nodeSize.width}" height="${nodeSize.height}"
            fill="${fill}" stroke="${stroke}" stroke-width="1.5" />
          <text x="${node.x + 12}" y="${node.y + 22}" class="vnt-node-label">${node.label}</text>
          <text x="${node.x + 12}" y="${node.y + 42}" class="vnt-node-value">${node.value}</text>
          ${timeLines}
          ${extraLines}
        </g>
      `;
    };

    const svgContent = `
      <svg class="vnt-flow-svg" viewBox="0 0 ${baseSize.width} ${baseSize.height}"
        preserveAspectRatio="xMidYMid meet"
        width="${baseSize.width}" height="${baseSize.height}"
        style="transform: scale(${SCALE}); transform-origin: top left;">
        <defs>${arrowDefs}</defs>
        ${connections.map(linePath).join("")}
        ${nodes.map(nodeTemplate).join("")}
      </svg>
    `;
    const svg = `
      <div class="vnt-flow-scaler" style="width:${scaledSize.width}px;height:${scaledSize.height}px;">
        ${svgContent}
      </div>
    `;

    $wrap.html(`
      <div class="vnt-flow-container">
        <style>
          .vnt-flow-container { width: 100%; max-width: 100%; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; background: #f8fafc; overflow-x: auto; }
          .vnt-flow-legend { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 6px; font-size: 12px; color: #475569; }
          .vnt-flow-legend .vnt-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 999px; background: #fff; }
          .vnt-flow-legend .vnt-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
          .vnt-flow-scaler { max-width: 100%; }
          .vnt-flow-svg { display: block; }
          .vnt-node-label { font-size: 12px; font-weight: 600; fill: #475569; }
          .vnt-node-value { font-size: 14px; font-weight: 700; fill: #0f172a; }
          .vnt-node-status { font-size: 12px; font-weight: 600; }
          .vnt-node-time { font-size: 11px; fill: #64748b; }
          .vnt-node-extra { font-size: 11px; fill: #334155; font-weight: 600; }
          .vnt-flow-note { margin-top: 6px; font-size: 12px; color: #64748b; }
        </style>
        <div class="vnt-flow-legend">
          <div class="vnt-chip"><span class="vnt-dot" style="background:#22c55e"></span>Hoàn thành</div>
          <div class="vnt-chip"><span class="vnt-dot" style="background:#3b82f6"></span>Đang xử lý</div>
          <div class="vnt-chip"><span class="vnt-dot" style="background:#f59e0b"></span>Trả lại</div>
          <div class="vnt-chip"><span class="vnt-dot" style="background:#e85b5b"></span>Quá hạn</div>
          <div class="vnt-chip"><span class="vnt-dot" style="background:#94a3b8"></span>Chưa có trạng thái</div>
        </div>
        ${svg}
        
      </div>
    `);
  }
});

// Child table hooks: VNT Document Management Item2 (items)
frappe.ui.form.on("VNT Document Management Item2", {
  chu_tri(frm, cdt, cdn) {
    enforce_single_role(cdt, cdn, "chu_tri");
    ensure_single_chair_row(frm, cdt, cdn);
    frm.trigger("sync_chair_from_items");
    frm.trigger("sync_collab_from_items");
  },
  employee(frm) {
    frm.trigger("sync_chair_from_items");
    frm.trigger("sync_collab_from_items");
  },
  deadline(frm, cdt, cdn) {
    ensure_item_deadline_within_parent(frm, cdt, cdn);
    frm.trigger("sync_chair_from_items");
    frm.trigger("sync_collab_from_items");
  },
  phoi_hop(frm, cdt, cdn) {
    enforce_single_role(cdt, cdn, "phoi_hop");
    frm.trigger("sync_collab_from_items");
  },
  nhan_de_biet(frm, cdt, cdn) {
    enforce_single_role(cdt, cdn, "nhan_de_biet");
    frm.trigger("sync_collab_from_items");
  }
});

// Child table hooks: VNT Document Management Item (items2)
frappe.ui.form.on("VNT Document Management Item", {
  cv_xu_ly(frm, cdt, cdn) {
    const row = (locals[cdt] && locals[cdt][cdn]) || null;
    const hasAssignedField = !!frappe.get_meta(cdt)?.fields?.some((df) => df.fieldname === "cv_xu_ly_assigned_at");
    if (!row) return;
    if (row.cv_xu_ly) {
      const now = frappe.datetime.now_datetime();
      if (hasAssignedField) {
        frappe.model.set_value(cdt, cdn, "cv_xu_ly_assigned_at", now);
      } else {
        row.cv_xu_ly_assigned_at = now;
      }
    } else if (row.cv_xu_ly_assigned_at) {
      if (hasAssignedField) {
        frappe.model.set_value(cdt, cdn, "cv_xu_ly_assigned_at", null);
      } else {
        row.cv_xu_ly_assigned_at = null;
      }
    }
    frm.trigger("render_process_flow");
  },
  trang_thai_nguoi_phoi_hop(frm, cdt, cdn) {
    ensure_collab_not_done_before_specialist(cdt, cdn);
    const row = (locals[cdt] && locals[cdt][cdn]) || null;
    const hasCompletedField = !!frappe.get_meta(cdt)?.fields?.some((df) => df.fieldname === "nguoi_phoi_hop_completed_at");
    if (row) {
      if (is_done(row.trang_thai_nguoi_phoi_hop) && !row.nguoi_phoi_hop_completed_at) {
        if (hasCompletedField) {
          frappe.model.set_value(cdt, cdn, "nguoi_phoi_hop_completed_at", frappe.datetime.now_datetime());
        } else {
          row.nguoi_phoi_hop_completed_at = frappe.datetime.now_datetime();
        }
      } else if (!is_done(row.trang_thai_nguoi_phoi_hop) && row.nguoi_phoi_hop_completed_at) {
        if (hasCompletedField) {
          frappe.model.set_value(cdt, cdn, "nguoi_phoi_hop_completed_at", null);
        } else {
          row.nguoi_phoi_hop_completed_at = null;
        }
      }
    }
    frm.trigger("render_process_flow");
  },
  trang_thai_cv_xu_ly(frm, cdt, cdn) {
    const row = (locals[cdt] && locals[cdt][cdn]) || null;
    const hasCompletedField = !!frappe.get_meta(cdt)?.fields?.some((df) => df.fieldname === "cv_xu_ly_completed_at");
    if (row) {
      if (is_done(row.trang_thai_cv_xu_ly) && !row.cv_xu_ly_completed_at) {
        if (hasCompletedField) {
          frappe.model.set_value(cdt, cdn, "cv_xu_ly_completed_at", frappe.datetime.now_datetime());
        } else {
          row.cv_xu_ly_completed_at = frappe.datetime.now_datetime();
        }
      } else if (!is_done(row.trang_thai_cv_xu_ly) && row.cv_xu_ly_completed_at) {
        if (hasCompletedField) {
          frappe.model.set_value(cdt, cdn, "cv_xu_ly_completed_at", null);
        } else {
          row.cv_xu_ly_completed_at = null;
        }
      }
    }
    frm.trigger("render_process_flow");
  },
  deadline2(frm, cdt, cdn) {
    ensure_spec_deadline_within_collab(cdt, cdn);
  }
});

// Child table hooks: VNT Document Management Item3 (items3, item4)
frappe.ui.form.on("VNT Document Management Item3", {
  attach(_frm, cdt, cdn) {
    const row = locals[cdt] && locals[cdt][cdn];
    if (!row || !row.attach) return;
    const currentUser = frappe.session?.user || null;
    if (!currentUser) return;
    if (row.user === currentUser) return;
    frappe.model.set_value(cdt, cdn, "user", currentUser);
  }
});

const clear_invalid_opinion_selection = (frm, row) => {
  // Khi user chọn opinion không hợp lệ (không đúng quyền), xóa ngay giá trị vừa chọn.
  if (!row || !row.parentfield) return;
  row.opinion = "";
  frm.refresh_field(row.parentfield);
};

// Child table hooks: VNT Document Management Item6 (items6)
frappe.ui.form.on("VNT Document Management Item6", {
  async opinion(frm, cdt, cdn) {
    const row = (locals[cdt] && locals[cdt][cdn]) || null;
    if (!row) return;
    const currentEmp = await get_current_employee(frm);

    // items6: mỗi employee chỉ sửa opinion của mình.
    if (row.parentfield === "items6") {
      const leadEmp = (frm.doc.lead_depart || "").trim();
      if (!can_edit_items6_opinion(row, currentEmp, leadEmp)) {
        // Sai quyền: xóa giá trị vừa chọn trước khi cảnh báo.
        clear_invalid_opinion_selection(frm, row);
        sync_summary_opinion(frm);
        apply_items7_visibility(frm);
        frappe.throw("Bạn chỉ được chọn ý kiến của chính mình.");
        return;
      }
      sync_summary_opinion(frm);
      apply_items7_visibility(frm);
      return;
    }

    // items7:
    // - VGT00068/VGT00072 chỉ lead_depart sửa.
    // - 5 thành viên còn lại chỉ sửa opinion của chính mình.
    if (row.parentfield === "items7") {
      const leadEmp = (frm.doc.lead_depart || "").trim();
      const manualPairCompleted = is_items7_manual_pair_completed(frm);
      // Chưa đủ opinion của 2 mã SCIC thì chặn member còn lại nhập và cảnh báo rõ nguyên nhân.
      if (!SCIC_MANUAL_EMPLOYEES.has((row.employee || "").trim()) && !manualPairCompleted) {
        clear_invalid_opinion_selection(frm, row);
        frappe.throw("Vui lòng điền ý kiến của các thành viên SCIC trước khi các thành viên còn lại nhập ý kiến.");
        return;
      }
      if (!can_edit_items7_opinion(row, currentEmp, leadEmp, manualPairCompleted)) {
        // Sai quyền: xóa giá trị vừa chọn trước khi cảnh báo.
        clear_invalid_opinion_selection(frm, row);
        frappe.throw("Bạn không có quyền sửa ý kiến của dòng này.");
        return;
      }
      // Sau khi 2 mã SCIC đổi opinion, refresh lại scope để mở/khóa đúng ngay trên UI.
      frm.trigger("enforce_items7_opinion_scope");
    }
  },
  form_render(frm) {
    frm.trigger("enforce_items6_opinion_scope");
    frm.trigger("enforce_items7_opinion_scope");
  }
});

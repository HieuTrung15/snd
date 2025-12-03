// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

// Tìm phòng/ban của người chủ trì từ bảng người xử lý chính
const get_chair_department = (frm) => {
  const rows = Array.isArray(frm.doc.items) ? frm.doc.items : [];
  const chairRow = rows.find((r) => r.chu_tri);
  return chairRow?.department || null;
};

// Không cho phép thời hạn dòng vượt quá thời hạn chung của văn bản
const item_role_label = (row) => {
  if (!row) return "nhân sự";
  if (row.chu_tri) return "Người chủ trì";
  if (row.phoi_hop) return "Người phối hợp";
  if (row.nhan_de_biet) return "Nhận để biết";
  return "nhân sự";
};

// Đảm bảo chỉ có duy nhất một dòng được chọn Chủ trì
const ensure_single_chair_row = (frm, cdt, cdn) => {
  const row = (locals[cdt] && locals[cdt][cdn]) || null;
  if (!row || !row.chu_tri) return;

  const rows = Array.isArray(frm.doc.items) ? frm.doc.items : [];
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

const find_late_item_deadline = (frm) => {
  if (!frm.doc.deadline) return null;
  const rows = Array.isArray(frm.doc.items) ? frm.doc.items : [];
  const idx = rows.findIndex((row) => row.deadline && frappe.datetime.get_diff(row.deadline, frm.doc.deadline) > 0);
  if (idx === -1) return null;
  return { row: rows[idx], idx: idx + 1, typeLabel: item_role_label(rows[idx]) };
};

const find_multiple_chair = (frm) => {
  const rows = Array.isArray(frm.doc.items) ? frm.doc.items : [];
  const picked = rows.filter((r) => r.chu_tri);
  if (picked.length <= 1) return null;
  return picked;
};

frappe.ui.form.on("VNT Document Management", {
  setup(frm) {
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
  },

  chairperson(frm) {
    if (frm.doc.chairperson) {
      frm.set_value("nguoi_chu_tri", frm.doc.chairperson);
    }
  },



  refresh(frm) {
    // Luôn reset viewer mỗi lần refresh
    frm.trigger("render_attach");
    frm.trigger("sync_chair_from_items");
    frm.trigger("sync_collab_from_items");
    frm.trigger("render_process_flow");
    frm.trigger("setup_cv_xu_ly_query");
    frm.trigger("setup_cv_xu_ly_query_items2");
    frm.trigger("lock_items2_grid");

    // Chỉ set mặc định khi là phiếu mới
    if (frm.is_new()) {
      if (!frm.doc.employee) {
        frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name")
          .then(r => r?.message?.name && frm.set_value("employee", r.message.name));
      }
      if (!frm.doc.date) {
        frm.set_value("date", frappe.datetime.now_date());
      }
      frm.trigger("prefill_level1_approvers");
    }
  },

  // thay đổi naming series khi đổi loại văn bản
  type(frm) {
    if (frm.doc.type == "Công văn đến") {
      frm.set_value("naming_series", "CVĐEN.-.MM..YY.-.####");
    }
    else if (frm.doc.type == "Công văn đi") {
      frm.set_value("naming_series", "CVĐI.-.MM..YY.-.####");
    } else {
      frm.set_value("naming_series", "VBNB.-.MM..YY.-.####");
    }
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
  },

  employee_status(frm) {
    frm.trigger("render_process_flow");
  },

  handler_status(frm) {
    frm.trigger("render_process_flow");
  },

  chairperson(frm) {
    frm.trigger("render_process_flow");
  },

  chairperson_status(frm) {
    frm.trigger("render_process_flow");
  },

  collaborator(frm) {
    frm.trigger("render_process_flow");
  },

  collaborator_status(frm) {
    frm.trigger("render_process_flow");
  },

  cv_xu_ly(frm) {
    frm.trigger("render_process_flow");
  },

  trang_thai_chuyen_vien_xu_ly(frm) {
    frm.trigger("render_process_flow");
  },

  info_recipient(frm) {
    frm.trigger("render_process_flow");
  },

  info_recipient_status(frm) {
    frm.trigger("render_process_flow");
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
    const grid = frm.fields_dict.items2?.grid;
    if (!grid) return;
    grid.cannot_add_rows = true;
    grid.cannot_delete_rows = true;
    grid.wrapper.find(".grid-add-row, .grid-remove-rows, .grid-remove-all-rows").hide();
  },

  sync_chair_from_items(frm) {
    const rows = Array.isArray(frm.doc.items) ? frm.doc.items : [];
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
  },

  sync_collab_from_items(frm) {
    const srcRows = (frm.doc.items || []).filter(r => r.phoi_hop);
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
      } else if (!row.trang_thai_nguoi_phoi_hop) {
        row.trang_thai_nguoi_phoi_hop = "Đang xử lý";
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
    if (Array.isArray(frm.doc.items) && frm.doc.items.length) return; // avoid overriding manual rows

    frappe.call({
      method: "vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.get_level1_approvers",
      freeze: false,
      callback: (r) => {
        const rows = r?.message || [];
        if (!rows.length) return;
        frm.clear_table("items");
        rows.forEach((item) => {
          const row = frm.add_child("items");
          row.employee = item.employee;
          row.department = item.department;
        });
        frm.refresh_field("items");
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
    addId(frm.doc.chairperson);
    addId(frm.doc.cv_xu_ly);
    const rowsMain = Array.isArray(frm.doc.items) ? frm.doc.items : [];
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

    const missing = [...ids].filter((id) => !nameCache[id]);
    if (missing.length && !frm._empNameLoading) {
      frm._empNameLoading = true;
      frappe.call({
        method: "frappe.client.get_list",
        args: {
          doctype: "Employee",
          filters: [["name", "in", missing]],
          fields: ["name", "employee_name"],
          limit_page_length: missing.length
        },
        callback: (r) => {
          const res = r?.message || [];
          const found = new Set();
          res.forEach((emp) => {
            nameCache[emp.name] = emp.employee_name || emp.name;
            found.add(emp.name);
          });
          missing.forEach((id) => {
            if (!found.has(id)) nameCache[id] = id;
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

    const SCALE = 0.85;
    const stackSpacing = 120;
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
      return "#f8fafc";
    };

    const today = frappe.datetime.get_today();
    const isOverdue = (deadline, statusVal) => {
      if (!deadline) return false;
      if ((statusVal || "").trim() === "Hoàn thành") return false;
      return deadline < today;
    };

    const colorForNode = (node) => {
      // Văn thư luôn xanh hoàn thành
      if (node.key === "employee") return "#22c55e";

      if (node.statusKey) {
        const currentStatus = (frm.doc[node.statusKey] || "").trim();
        // Lãnh đạo tập đoàn: xanh khi trạng thái "Chuyển văn bản"
        if (node.key === "handler" && currentStatus === "Chuyển văn bản") {
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
        roleNodes.push({
          key: `${roleKey}-${idx}`,
          label,
          value,
          stroke: color,
          statusLabel: statusText,
          showStatus,
          x,
          y: startY + count * stackSpacing
        });
        count += 1;
      });
      return count;
    };

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
        colorForRow: (row) => (row.nhan_de_biet ? "#22c55e" : "#111827")
      }
    );

    const lastStackEnd = infoStart + Math.max(infoCount, 1) * stackSpacing;
    // Giảm khoảng trống đáy để không dư quá nhiều
    baseSize.height = Math.max(420, lastStackEnd + 60);

    const nodeSize = { width: 180, height: 80 };

    const nodes = [
      {
        key: "employee",
        label: "Văn thư",
        value: displayEmployee(frm.doc.employee),
        stroke: "#3b82f6",
        fill: "#e0ecff",
        statusKey: "employee_status",
        x: 18,
        y: 108
      },
      {
        key: "handler",
        label: "Lãnh Đạo Tập Đoàn",
        value: displayEmployee(frm.doc.handler),
        stroke: "#f59e0b",
        fill: "#fef3c7",
        statusKey: "handler_status",
        showStatus: false,
        x: 320,
        y: 108
      }
    ];

    const hasPrimarySpecialist = chairCount > 0 && (frm.doc.cv_xu_ly || "").trim();
    if (hasPrimarySpecialist) {
      const primaryOverdue = isOverdue(frm.doc.deadline_cv_xu_ly, frm.doc.trang_thai_chuyen_vien_xu_ly);
      nodes.push({
        key: "specialist_primary",
        label: "Chuyên viên xử lý",
        value: displayEmployee(frm.doc.cv_xu_ly),
        stroke: primaryOverdue ? "#e85b5b" : statusColorValue(frm.doc.trang_thai_chuyen_vien_xu_ly || ""),
        fill: primaryOverdue
          ? fillByStroke("#e85b5b")
          : fillByStroke(statusColorValue(frm.doc.trang_thai_chuyen_vien_xu_ly || "")),
        statusKey: "trang_thai_chuyen_vien_xu_ly",
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
      nodes.push({
        key: specKey,
        label: "Chuyên viên xử lý",
        value: displayEmployee(row.cv_xu_ly),
        stroke,
        fill: fillByStroke(stroke),
        statusKey: null,
        statusLabel: overdue ? "Quá hạn" : row.trang_thai_cv_xu_ly || "",
        showStatus: true,
        x: specialistX,
        y: baseY
      });
    });

    nodes.push(...roleNodes);

    // Tính chiều rộng bám sát nút xa nhất để tránh vùng trống dư
    const maxNodeRight = nodes.reduce((max, n) => Math.max(max, n.x + nodeSize.width), 0);
    baseSize.width = Math.max(maxNodeRight + 80, 480);
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
          connections.push({
            from: node.key,
            to: "specialist_primary",
            statusKey: "trang_thai_chuyen_vien_xu_ly",
            dashed: false
          });
        }
      }
      if (node.key.startsWith("collaborator")) {
        const idx = node.key.split("-")[1];
        const specKey = `specialist_collab-${idx}`;
        const targetExists = nodes.find((n) => n.key === specKey);
        if (targetExists) {
          connections.push({
            from: node.key,
            to: specKey,
            statusKey: null,
            color: statusColorValue(rowsCollab[idx]?.trang_thai_cv_xu_ly),
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
      const statusPart = () => {
        if (node.showStatus === false) return "";
        if (node.statusLabel !== undefined) {
          const color = statusColorValue(node.statusLabel);
          return `<text x="${node.x + 12}" y="${node.y + 72}" class="vnt-node-status" fill="${color}">
            ${node.statusLabel || ""}
          </text>`;
        }
        const info = node.statusKey ? statusInfo(node.statusKey) : { label: "", color: "#94a3b8" };
        return `<text x="${node.x + 12}" y="${node.y + 72}" class="vnt-node-status" fill="${info.color}">
          ${info.label}
        </text>`;
      };

      const stroke = colorForNode(node);
      const fill = fillByStroke(stroke);

      return `
        <g class="vnt-node" data-role="${node.key}">
          <rect x="${node.x}" y="${node.y}" rx="10" ry="10" width="${nodeSize.width}" height="${nodeSize.height}"
            fill="${fill}" stroke="${stroke}" stroke-width="1.5" />
          <text x="${node.x + 12}" y="${node.y + 24}" class="vnt-node-label">${node.label}</text>
          <text x="${node.x + 12}" y="${node.y + 48}" class="vnt-node-value">${node.value}</text>
          ${statusPart()}
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
          .vnt-flow-note { margin-top: 6px; font-size: 12px; color: #64748b; }
        </style>
        <div class="vnt-flow-legend">
          <div class="vnt-chip"><span class="vnt-dot" style="background:#22c55e"></span>Hoàn thành</div>
          <div class="vnt-chip"><span class="vnt-dot" style="background:#3b82f6"></span>Đang xử lý</div>
          <div class="vnt-chip"><span class="vnt-dot" style="background:#f59e0b"></span>Trả lại</div>
          <div class="vnt-chip"><span class="vnt-dot" style="background:#e85b5b"></span>Quá hạn</div>
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

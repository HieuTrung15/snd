// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Document Management", {
  chairperson(frm) {
    if (frm.doc.chairperson) {
      frm.set_value("nguoi_chu_tri", frm.doc.chairperson);
    }
  },



  refresh(frm) {
    // Luôn reset viewer mỗi lần refresh
    frm.trigger("render_attach");
    frm.trigger("render_process_flow");

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

    const SCALE = 1;
    const baseSize = { width: 1100, height: 420 };
    const scaledSize = {
      width: Math.round(baseSize.width * SCALE),
      height: Math.round(baseSize.height * SCALE)
    };

    const displayValue = (key) => {
      const raw = frm.doc[`${key}_name`] || frm.doc[key] || "";
      return raw ? frappe.utils.escape_html(raw) : "Chưa chọn";
    };

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
      return "#e85b5b";
    };

    const statusInfo = (key) => ({
      label: statusLabel(key),
      color: statusColor(key)
    });

    const fillByStroke = (color) => {
      if (color === "#22c55e") return "#e8f8f0"; // green
      if (color === "#f59e0b") return "#fef3c7"; // yellow
      if (color === "#e85b5b") return "#fee2e2"; // red
      if (color === "#94a3b8") return "#e5e7eb"; // grey/empty
      return "#f8fafc";
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

    const nodeSize = { width: 200, height: 104 };

    const nodes = [
      {
        key: "employee",
        label: "Văn thư",
        value: displayValue("employee"),
        stroke: "#3b82f6",
        fill: "#e0ecff",
        statusKey: "employee_status",
        x: 18,
        y: 108
      },
      {
        key: "handler",
        label: "Lãnh Đạo Tập Đoàn",
        value: displayValue("handler"),
        stroke: "#f59e0b",
        fill: "#fef3c7",
        statusKey: "handler_status",
        showStatus: false,
        x: 280,
        y: 108
      },
      {
        key: "chairperson",
        label: "Người chủ trì",
        value: displayValue("chairperson"),
        stroke: "#22c55e",
        fill: "#e8f8f0",
        statusKey: "chairperson_status",
        x: 560,
        y: 24
      },
      {
        key: "collaborator",
        label: "Người phối hợp",
        value: displayValue("collaborator"),
        stroke: "#16a34a",
        fill: "#e8f8f0",
        statusKey: "collaborator_status",
        x: 560,
        y: 150
      },
      {
        key: "info_recipient",
        label: "Nhận để biết",
        value: displayValue("info_recipient"),
        stroke: "#111827",
        fill: "#e5e7eb",
        statusKey: "info_recipient_status",
        showStatus: false,
        x: 560,
        y: 276
      },
      {
        key: "specialist_primary",
        label: "Chuyên viên xử lý",
        value: displayValue("cv_xu_ly"),
        stroke: "#0ea5e9",
        fill: "#e0f2fe",
        statusKey: "trang_thai_chuyen_vien_xu_ly",
        x: 840,
        y: 24
      },
      {
        key: "specialist_collab",
        label: "Chuyên viên xử lý",
        value: displayValue("cv_xu_ly"),
        stroke: "#0ea5e9",
        fill: "#e0f2fe",
        statusKey: "cv_xu_ly_status",
        x: 840,
        y: 150
      }
    ];

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
      { from: "employee", to: "handler", color: "#22c55e", dashed: false },
      { from: "handler", to: "chairperson", statusKey: "chairperson_status", dashed: false },
      { from: "handler", to: "collaborator", statusKey: "collaborator_status", dashed: false },
      { from: "handler", to: "info_recipient", statusKey: "info_recipient_status", dashed: true },
      { from: "chairperson", to: "specialist_primary", statusKey: "trang_thai_chuyen_vien_xu_ly", dashed: false },
      { from: "collaborator", to: "specialist_collab", statusKey: "cv_xu_ly_status", dashed: false }
    ];

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
          .vnt-flow-container { border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; background: #f8fafc; }
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
        ${svg}
        
      </div>
    `);
  }
});

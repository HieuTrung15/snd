frappe.listview_settings["VNT Recruitment Proposal"] = {
  add_fields: ["status"],
  has_indicator_for_draft: true,
  has_indicator_for_cancelled: true,
  get_indicator(doc) {
    const statusColors = {
      "Mới tạo": "gray",
      "Chờ phê duyệt": "orange",
      "Đã phê duyệt": "green",
      "Từ chối": "red",
    };

    const status = doc.status || __("Không xác định", null, "VNT Recruitment Proposal");
    const color = statusColors[doc.status] || "gray";
    const filter = doc.status ? `status,=,${doc.status}` : null;

    return [__(status, null, "VNT Recruitment Proposal"), color, filter];
  },
};

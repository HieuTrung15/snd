frappe.views.calendar["VNT Car Registration"] = {
  fields: [
    "expected_start_date",
    "expected_end_date",
    "status",
    "name",
    "project_name",
    "custom_calendar_title"  // field bạn mới thêm
  ],
  field_map: {
    start: "expected_start_date",
    end: "expected_end_date",
    id: "name",
    title: "custom_calendar_title",   // dùng field custom
    allDay: "allDay",
    progress: "progress"
  },
  gantt: true,
  filters: [

  ],
  get_events_method: "frappe.desk.calendar.get_events",
  get_css_class: function (data) {
    console.log("dâta", data)
    if (data.status === "Completed") {
      return "success";
    } else if (data.status === "Open") {
      return "info";
    } else if (data.status === "Cancelled") {
      return "primary";
    }
  }
};

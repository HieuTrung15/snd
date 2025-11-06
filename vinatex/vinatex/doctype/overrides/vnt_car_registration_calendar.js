frappe.views.calendar["VNT Car Registration"] = {
  field_map: {
    start: "start",
    end: "end",
    id: "name",
    title: "title",
    allDay: "allDay",
  },

  fields: [
  ],

  get_events_method: "vinatex.vinatex.doctype.overrides.vnt_car_registration_calendar.get_vnt_car_registration_events",

  filters: [
    {
      fieldtype: "Data",
      fieldname: "driver",
      label: __("Lái xe"),
    },
  ],

  get_css_class: function (data) {
    console.log("dât", data)
    if (data.status === "Completed") return "success";
    if (data.status === "Open") return "info";
    if (data.status === "Cancelled") return "danger";
  },
};

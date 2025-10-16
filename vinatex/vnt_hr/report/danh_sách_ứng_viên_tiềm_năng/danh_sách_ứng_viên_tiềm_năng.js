// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh sách ứng viên tiềm năng"] = {
	"filters": [
    {
      "fieldname": "from_date",
      "label": "From Date",
      "fieldtype": "Date",
      "default": frappe.datetime.month_start()
    },
    {
      "fieldname": "to_date",
      "label": "To Date",
      "fieldtype": "Date",
      "default": frappe.datetime.get_today()
    },
    {
      "fieldname": "department",
      "label": "Department",
      "fieldtype": "Link",
      "options": "Department"
    },
    {
      "fieldname": "job_opening",
      "label": "Job Opening",
      "fieldtype": "Link",
      "options": "Job Opening"
    },
    {
      "fieldname": "status",
      "label": "Status",
      "fieldtype": "Select",
      "options": "\nCV\nDuyệt CV\nPhỏng vấn\nThi tuyển\nHoàn thành\nLoại"
    },
    {
      "fieldname": "potential_level",
      "label": "Potential Level",
      "fieldtype": "Select",
      "options": "\nHigh\nMedium\nLow"
      // Chỉ có tác dụng nếu hệ có field custom_potential_level
    }
]
};
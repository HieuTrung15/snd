app_name = "vinatex"
app_title = "vinatex"
app_publisher = "vinatex"
app_description = "vinatex"
app_email = "sonph@vinatex.com.vn"
app_license = "mit"
from frappe import conf
version = conf.get("asset_version") or 1
# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "vinatex",
# 		"logo": "/assets/vinatex/logo.png",
# 		"title": "vinatex",
# 		"route": "/vinatex",
# 		"has_permission": "vinatex.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/vinatex/css/chart.css"
app_include_css = [
    f"/assets/vinatex/css/theme.css?v={version}",
    f"/assets/vinatex/css/custom_notification.css?v={version}"
]
app_include_js = [
    f"/assets/vinatex/js/global_header.js?v={version}",
	f"/assets/vinatex/js/title-wrap.js?v={version}",
	f"/assets/vinatex/js/report_actions_override.js?v={version}",
	f"/assets/vinatex/js/fullWidth.js?v={version}",
    f"/assets/vinatex/js/workspace_redirects.js?v={version}",
    f"/assets/vinatex/js/custom_notification.js?v={version}",
    f"/assets/vinatex/js/hide_id_column.js?v={version}",
    f"/assets/vinatex/js/hide_connections.js?v={version}",
]

# include js, css files in header of web template
# web_include_css = "/assets/vinatex/css/vinatex.css"
# web_include_js = "/assets/vinatex/js/vinatex.js"
web_include_js = [
    f"/assets/vinatex/js/nav_home.js?v={version}",
]


# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "vinatex/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
page_js = {
    "leadership-dashboard": "vinatex/vnt_hr/page/leadership_dashboard/leadership_dashboard.js",
    "test": "vinatex/vnt_hr/page/test/test.js",
}
override_whitelisted_methods = {
    # method gốc của HRMS → method của bạn
    "hrms.hr.doctype.leave_application.leave_application.get_leave_approver":
    "vinatex.vinatex.doctype.overrides.leave_application.get_leave_approver"
}

override_doctype_class = {
    "Leave Application": "vinatex.vinatex.doctype.overrides.leave_application.VntLeaveApplication",
    "Leave Allowcation": "vinatex.vinatex.doctype.overrides.leave_allowcation.VntLeaveAllocation",
	"Attendance": "vinatex.vinatex.doctype.overrides.attendance.VntAttendance",
    "Employee": "vinatex.vinatex.doctype.overrides.employee.VntEmployee",
    "User": "vinatex.vinatex.doctype.overrides.user.CustomUser",
    "Holiday List": "vinatex.vinatex.doctype.overrides.holiday_list.VntHolidayList",
    "Item": "vinatex.vinatex.doctype.overrides.item.VntItem",
}

# include js in doctype views
doctype_js = {
    # "doctype" : "public/js/doctype.js"
    "Leave Application": "vinatex/doctype/overrides/leave_application.js",
    "Employee": "vinatex/doctype/overrides/employee.js",
	"ToDo": "vinatex/doctype/overrides/todo.js",
	"User": "vinatex/doctype/overrides/user.js",
	"Job Requisition": "vinatex/doctype/overrides/job_requisition.js",
	"Job Applicant": "doctype/overrides/job_applicant.js",
	"VNT Applicant Headhunter Rating": "vinatex/vnt_hr/doctype/vnt_applicant_headhunter_rating/vnt_applicant_headhunter_rating.js",
	"VNT CVE Source": "vinatex/public/js/vnt_itsec/vnt_cve_source.js",
	"VNT Vulnerability Advisory": "vinatex/public/js/vnt_itsec/vnt_vulnerability_advisory.js",
	"VNT CVE": "vinatex/public/js/vnt_itsec/vnt_cve.js",
}
doctype_list_js = {
    "VNT Salary Slip": "vinatex/vnt_hr/doctype/vnt_salary_slip/vnt_salary_slip_list.js",
    "VNT 13th Month Salary": "vinatex/vnt_hr/doctype/vnt_13th_month_salary/vnt_13th_month_salary_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
doctype_calendar_js = {"VNT Car Registration" : "vinatex/doctype/overrides/vnt_car_registration_calendar.js"}
jinja = {
    "methods": [
        "vinatex.vinatex.doctype.utils.numword_vi.number_to_words"
    ]
}
# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "vinatex/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "vinatex.utils.jinja_methods",
# 	"filters": "vinatex.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "vinatex.install.before_install"
# after_install = "vinatex.vnt_itsec.install.bootstrap"

# Uninstallation
# ------------

# before_uninstall = "vinatex.uninstall.before_uninstall"
# after_uninstall = "vinatex.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "vinatex.utils.before_app_install"
# after_app_install = "vinatex.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "vinatex.utils.before_app_uninstall"
# after_app_uninstall = "vinatex.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "vinatex.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
    "VNT Salary Slip": "vinatex.vnt_hr.permissions.salary_slip_permission_query_conditions",
    "ToDo": "vinatex.vnt_hr.permissions.get_permission_query_conditions",
    "VNT Monthly Payroll": "vinatex.vnt_hr.permissions.vnt_monthly_payroll_per",
    "VNT 13th Month Salary": "vinatex.vnt_hr.permissions.vnt_monthly_payroll_per",
    "VNT Document Management": "vinatex.vnt_hr.permissions.vnt_document_management_permission_query_conditions",
}

has_permission = {
    "VNT Salary Slip": "vinatex.vnt_hr.permissions.salary_slip_has_permission",
    "VNT Monthly Payroll": "vinatex.vnt_hr.permissions.vnt_monthly_payroll_has_permission",
    "VNT 13th Month Salary": "vinatex.vnt_hr.permissions.vnt_13th_month_salary_has_permission",
    "VNT New Feed": "vinatex.vnt_hr.permissions.vnt_new_feed_has_permission",
    "VNT Document Management": "vinatex.vnt_hr.permissions.vnt_document_management_has_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }
doc_events = {
	"Job Applicant": {
		"validate": "vinatex.vnt_hr.job_applicant_rating.validate_job_applicant_rating",
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "cron": {
        "30 1 * * *": [
            "vinatex.vnt_itsec.sync.run.run_nightly",
        ],
        "15 2 * * *": [
            "vinatex.vnt_itsec.cleanup.cleanup_cves",
        ],
        "0 3 1 * *": [
            "vinatex.vnt_itsec.sync.run.run_monthly_backfill",
        ],
        "0 4 1 1 *": [
            "vinatex.vinatex.doctype.overrides.allocate_leave.allocate_leave"
        ],
		# Chạy chấm công 10p/lân từ 9h đến 10h sáng hàng ngày
		"*/30 9-10 * * *": [
			"vinatex.vinatex.doctype.overrides.timekeeping.get_timekeeping_data_morning",
		],
		# Chạy chấm công lúc 1h sáng hàng ngày
        "5 0 * * *": [
			"vinatex.vinatex.doctype.overrides.timekeeping.get_timekeeping_data_evening",
		],
        # "5 11 * * *": [
		# 	"vinatex.vinatex.doctype.overrides.timekeeping.get_timekeeping_data_evening",
		# ],
		"15 0 * * *": [
			"vinatex.vinatex.doctype.overrides.attendance.create_attendance_from_checkin",
		],
        # "00 01 1 * *": [
        #     "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm",
        # ],
        "0 7 * * *": [
            "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm",
        ],
		# Nhắc hạn điền opinion items6/items7 (D-1 và D0) mỗi ngày.
		"30 7 * * *": [
			"vinatex.vnt_hr.doctype.vnt_document_management.vnt_document_management.notify_pending_hdqt_opinion_deadline",
		],
		"0 7 4 * *": [
			# "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm._cron_submit_attendance_confirm",
		],
		#Chạy tính lại tuổi hàng năm
		"00 01 1 1 *": [
            "vinatex.vinatex.doctype.overrides.retire_update.recalc_retirement_dates",
        ],
        # Tự động đánh dấu đã chuyển lương lúc 05:00 sáng ngày 06 hằng tháng
        "0 5 6 * *": [
            "vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll.auto_mark_salary_transferred",
        ],
    }

	# "all": [
	# 	"vinatex.tasks.all"
	# ],
	# "daily": [
	# 	"vinatex.tasks.daily"
	# ],
	# "hourly": [
	# 	"vinatex.tasks.hourly"
	# ],
	# "weekly": [
	# 	"vinatex.tasks.weekly"
	# ],
	# "monthly": [
	# 	"vinatex.tasks.monthly"
	# ],
}

# Testing
# -------

# before_tests = "vinatex.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "vinatex.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "vinatex.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["vinatex.utils.before_request"]
# after_request = ["vinatex.utils.after_request"]
# boot_session = "vinatex.api.boot.boot_session"

# Job Events
# ----------
# before_job = ["vinatex.utils.before_job"]
# after_job = ["vinatex.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"vinatex.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# override_doctype_class = {
#     "Leave Application": "vinatex.vinatex.doctype.overrides.leave_application.VntLeaveApplication",
#     "Leave Allocation": "vinatex.vinatex.doctype.overrides.leave_allocation.VntLeaveAllocation"
# }

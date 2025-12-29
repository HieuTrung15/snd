import frappe
from frappe.utils import nowdate

@frappe.whitelist()
def get_recruitment_dashboard(company=None, department=None, year=None, plan=None):
	"""
	Return JSON for Recruitment dashboard:
	- KPI counts
	- monthly trends
	- pipeline breakdown
	- latest lists
	"""

	filters = []
	params = {}

	if company:
		filters.append("company = %(company)s")
		params["company"] = company

	if department:
		# Job Requisition + Job Opening usually have department
		filters.append("department = %(department)s")
		params["department"] = department

	# Plan filter: Job Requisition has custom_recruitment_plan
	if plan:
		filters.append("custom_recruitment_plan = %(plan)s")
		params["plan"] = plan

	# year filter on posting_date / creation
	if not year:
		year = int(nowdate()[:4])
	params["year"] = int(year)

	where_jr = " AND ".join(filters) if filters else "1=1"

	# --- KPI: Job Requisition ---
	jr_total = frappe.db.sql(
		f"""
		select count(*) from `tabJob Requisition`
		where {where_jr} and year(posting_date) = %(year)s
		""",
		params,
	)[0][0]

	jr_by_status = frappe.db.sql(
		f"""
		select ifnull(status,'') as status, count(*) as cnt
		from `tabJob Requisition`
		where {where_jr} and year(posting_date) = %(year)s
		group by status
		order by cnt desc
		""",
		params,
		as_dict=True,
	)

	# --- KPI: Job Opening ---
	opening_filters = []
	opening_params = {"year": params["year"]}
	opening_join = ""
	if company:
		opening_filters.append("o.company = %(company)s")
		opening_params["company"] = company
	if department:
		opening_filters.append("o.department = %(department)s")
		opening_params["department"] = department
	if plan:
		if frappe.db.has_column("Job Opening", "custom_recruitment_plan"):
			opening_filters.append("o.custom_recruitment_plan = %(plan)s")
			opening_params["plan"] = plan
		elif frappe.db.has_column("Job Opening", "job_requisition"):
			opening_join = "left join `tabJob Requisition` jr on jr.name = o.job_requisition"
			opening_filters.append("jr.custom_recruitment_plan = %(plan)s")
			opening_params["plan"] = plan
	where_jo = " AND ".join(opening_filters) if opening_filters else "1=1"

	open_status_checks = ["ifnull(o.status,'') in ('Open','Opened')"]
	if frappe.db.has_column("Job Opening", "is_published"):
		open_status_checks.append("ifnull(o.is_published,0)=1")
	if frappe.db.has_column("Job Opening", "open"):
		open_status_checks.append("ifnull(o.open,0)=1")
	open_case = " or ".join(open_status_checks)

	jo_date_field = "o.posting_date" if frappe.db.has_column("Job Opening", "posting_date") else "o.creation"

	jo_total, jo_open = frappe.db.sql(
		f"""
		select
			count(*) as total,
			sum(case when {open_case} then 1 else 0 end) as open_cnt
		from `tabJob Opening` o
		{opening_join}
		where {where_jo} and year({jo_date_field}) = %(year)s
		""",
		opening_params,
	)[0]

	# --- KPI: Job Applicant ---
	# Applicant links to Job Opening; we filter applicant by opening (company/department/plan) via join
	app_filters = []
	app_params = {"year": params["year"]}
	app_join = ""
	if company:
		app_filters.append("o.company = %(company)s")
		app_params["company"] = company
	if department:
		app_filters.append("o.department = %(department)s")
		app_params["department"] = department
	if plan:
		if frappe.db.has_column("Job Opening", "custom_recruitment_plan"):
			app_filters.append("o.custom_recruitment_plan = %(plan)s")
			app_params["plan"] = plan
		elif frappe.db.has_column("Job Opening", "job_requisition"):
			app_join = "left join `tabJob Requisition` jr on jr.name = o.job_requisition"
			app_filters.append("jr.custom_recruitment_plan = %(plan)s")
			app_params["plan"] = plan
	app_where = " and " + " and ".join(app_filters) if app_filters else ""

	app_total = frappe.db.sql(
		f"""
		select count(*)
		from `tabJob Applicant` a
		left join `tabJob Opening` o on o.name = a.job_title
		{app_join}
		where year(a.creation) = %(year)s
		{app_where}
		""",
		app_params,
	)[0][0]

	app_by_status = frappe.db.sql(
		f"""
		select ifnull(a.status,'') as status, count(*) as cnt
		from `tabJob Applicant` a
		left join `tabJob Opening` o on o.name = a.job_title
		{app_join}
		where year(a.creation) = %(year)s
		{app_where}
		group by a.status
		order by cnt desc
		""",
		app_params,
		as_dict=True,
	)

	# --- Trends by month ---
	jr_trend = frappe.db.sql(
		f"""
		select month(posting_date) m, count(*) cnt
		from `tabJob Requisition`
		where {where_jr} and year(posting_date) = %(year)s
		group by month(posting_date)
		""",
		params,
		as_dict=True,
	)

	jo_trend = frappe.db.sql(
		f"""
		select month({jo_date_field}) m, count(*) cnt
		from `tabJob Opening` o
		{opening_join}
		where {where_jo} and year({jo_date_field}) = %(year)s
		group by month({jo_date_field})
		""",
		opening_params,
		as_dict=True,
	)

	# --- Latest applicants ---
	latest_applicants = frappe.db.sql(
		f"""
		select a.name, a.applicant_name, a.status, a.creation,
			   o.designation, o.department
		from `tabJob Applicant` a
		left join `tabJob Opening` o on o.name = a.job_title
		{app_join}
		where year(a.creation) = %(year)s
		{app_where}
		order by a.creation desc
		limit 5
		""",
		app_params,
		as_dict=True,
	)

	# --- Interview feedback pending (basic) ---
	# Depending on your setup, Interview Feedback links to Job Applicant / Interview.
	feedback_pending = frappe.db.sql(
		"""
		select count(*)
		from `tabInterview Feedback`
		where docstatus = 0 and year(creation) = %(year)s
		""",
		{"year": params["year"]},
	)[0][0]

	return {
		"year": params["year"],
		"kpi": {
			"jr_total": jr_total,
			"jr_by_status": jr_by_status,
			"jo_total": int(jo_total or 0),
			"jo_open": int(jo_open or 0),
			"app_total": app_total,
			"app_by_status": app_by_status,
			"feedback_pending": feedback_pending,
		},
		"trend": {
			"jr": jr_trend,
			"jo": jo_trend,
		},
		"lists": {
			"latest_applicants": latest_applicants,
		},
	}

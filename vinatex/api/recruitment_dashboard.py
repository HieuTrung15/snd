import frappe
from datetime import date
from frappe.utils import getdate, nowdate

PIPELINE_STAGES = [
	"Ứng viên",
	"Phỏng vấn",
	"Thi tuyển",
	"Phỏng vấn vòng 2",
	"Offer",
	"Nhân viên",
]

STAGE_ALIASES = {
	"ứng viên": "Ứng viên",
	"ung vien": "Ứng viên",
	"applicant": "Ứng viên",
	"applied": "Ứng viên",
	"apply": "Ứng viên",
	"open": "Ứng viên",
	"new": "Ứng viên",
	"shortlisted": "Phỏng vấn",
	"shortlist": "Phỏng vấn",
	"interview scheduled": "Phỏng vấn",
	"interview schedule": "Phỏng vấn",
	"schedule interview": "Phỏng vấn",
	"interview round 1": "Phỏng vấn",
	"pv": "Phỏng vấn",
	"phỏng vấn": "Phỏng vấn",
	"phong van": "Phỏng vấn",
	"interview": "Phỏng vấn",
	"pv vòng 1": "Phỏng vấn",
	"phỏng vấn vòng 1": "Phỏng vấn",
	"phong van vong 1": "Phỏng vấn",
	"thi tuyển": "Thi tuyển",
	"thi tuyen": "Thi tuyển",
	"thi test": "Thi tuyển",
	"test": "Thi tuyển",
	"written test": "Thi tuyển",
	"assessment": "Thi tuyển",
	"pv vòng 2": "Phỏng vấn vòng 2",
	"phỏng vấn vòng 2": "Phỏng vấn vòng 2",
	"phong van vong 2": "Phỏng vấn vòng 2",
	"interview round 2": "Phỏng vấn vòng 2",
	"second interview": "Phỏng vấn vòng 2",
	"offer": "Offer",
	"job offer": "Offer",
	"job offered": "Offer",
	"offer sent": "Offer",
	"offered": "Offer",
	"offer letter": "Offer",
	"replied": "Phỏng vấn",
	"nhân viên": "Nhân viên",
	"nhan vien": "Nhân viên",
	"nhận việc": "Nhân viên",
	"nhan viec": "Nhân viên",
	"joined": "Nhân viên",
	"onboarded": "Nhân viên",
	"employee": "Nhân viên",
	"hired": "Nhân viên",
	"accepted": "Offer",
}


def _normalize_stage(value):
	return (value or "").strip().lower()


def _map_stage(status, next_step):
	has_value = False
	for raw in (next_step, status):
		key = _normalize_stage(raw)
		if not key:
			continue
		has_value = True
		if key in STAGE_ALIASES:
			return STAGE_ALIASES[key]
	if ("pv" in key or "phỏng vấn" in key or "interview" in key) and "2" in key:
		return "Phỏng vấn vòng 2"
	if "phỏng vấn" in key or "interview" in key or key == "pv":
		return "Phỏng vấn"
	if "replied" in key:
		return "Phỏng vấn"
	if "thi" in key and "tuyển" in key:
		return "Thi tuyển"
	if "test" in key:
		return "Thi tuyển"
	if "offer" in key:
		return "Offer"
	if "accepted" in key:
		return "Offer"
	if "nhân viên" in key or "employee" in key or "hired" in key:
		return "Nhân viên"
		if "ứng viên" in key or "applicant" in key or "open" in key or "applied" in key:
			return "Ứng viên"
	return "Ứng viên" if has_value else ""


def _date_range(from_date, to_date, year=None):
	today = getdate(nowdate())
	if not from_date and not to_date and year:
		try:
			year_value = int(year)
		except Exception:
			year_value = today.year
		start = date(year_value, 1, 1)
		end = date(year_value, 12, 31)
	else:
		start = getdate(from_date) if from_date else date(today.year, 1, 1)
		end = getdate(to_date) if to_date else date(today.year, 12, 31)
	if start > end:
		start, end = end, start
	return start, end


def _applicant_date_expr():
	if frappe.db.has_column("Job Applicant", "custom_date"):
		return "coalesce(a.custom_date, date(a.creation))"
	return "date(a.creation)"


def _opening_date_expr():
	if frappe.db.has_column("Job Opening", "posting_date"):
		return "coalesce(o.posting_date, date(o.creation))"
	return "date(o.creation)"


def _opening_label_expr():
	if frappe.db.has_column("Job Opening", "job_title"):
		return "ifnull(o.job_title, o.name)"
	if frappe.db.has_column("Job Opening", "designation"):
		return "ifnull(o.designation, o.name)"
	return "o.name"


def _cost_field_expr():
	candidates = [
		"recruitment_cost",
		"total_recruitment_cost",
		"total_cost",
		"cost",
	]
	for fieldname in candidates:
		if frappe.db.has_column("Job Opening", fieldname):
			return f"o.{fieldname}"
	return None


def _month_labels():
	return [f"T{i}" for i in range(1, 13)]


def _series_by_month(rows, month_key="m", count_key="cnt"):
	series = [0] * 12
	for row in rows or []:
		m = int(row.get(month_key) or 0) - 1
		if 0 <= m < 12:
			series[m] = int(row.get(count_key) or 0)
	return series


def _turnover_chart(monthly_hired, monthly_left):
	return {
		"type": "line",
		"labels": _month_labels(),
		"datasets": [
			{"name": "Tuyển mới", "values": _series_by_month(monthly_hired)},
			{"name": "Nghỉ việc", "values": _series_by_month(monthly_left)},
		],
		"colors": ["#0ea5e9", "#ef4444"],
		"lineOptions": {"regionFill": 1, "hideDots": 0, "dotSize": 3},
	}


def _feedback_reason_expr():
	candidates = [
		"custom_rejection_reason",
		"custom_reason_for_rejection",
		"custom_reason",
		"rejection_reason",
		"reason_for_rejection",
		"reason",
	]
	for fieldname in candidates:
		if frappe.db.has_column("Interview Feedback", fieldname):
			return f"fb.{fieldname}"
	return "fb.feedback"


@frappe.whitelist()
def get_recruitment_dashboard(pos=None, source=None, from_date=None, to_date=None, year=None):
	from_date, to_date = _date_range(from_date, to_date, year=year)
	params_base = {"from_date": from_date, "to_date": to_date}

	app_date_expr = _applicant_date_expr()
	jo_date_expr = _opening_date_expr()

	app_filters = [
		f"{app_date_expr} between %(from_date)s and %(to_date)s",
		"a.docstatus < 2",
	]
	if pos:
		app_filters.append("a.job_title = %(pos)s")
	if source:
		app_filters.append("a.source = %(source)s")
	app_where = " and ".join(app_filters)

	app_params = dict(params_base)
	if pos:
		app_params["pos"] = pos
	if source:
		app_params["source"] = source

	total_applicants = frappe.db.sql(
		f"""
		select count(*) as cnt
		from `tabJob Applicant` a
		where {app_where}
		""",
		app_params,
	)[0][0] or 0

	open_status_checks = ["ifnull(o.status,'') in ('Open','Opened')"]
	if frappe.db.has_column("Job Opening", "is_published"):
		open_status_checks.append("ifnull(o.is_published,0)=1")
	if frappe.db.has_column("Job Opening", "open"):
		open_status_checks.append("ifnull(o.open,0)=1")
	open_case = " or ".join(open_status_checks)

	jo_filters = [
		f"{jo_date_expr} between %(from_date)s and %(to_date)s",
		"o.docstatus < 2",
	]
	if pos:
		jo_filters.append("o.name = %(pos)s")
	jo_where = " and ".join(jo_filters)

	jo_params = dict(params_base)
	if pos:
		jo_params["pos"] = pos

	open_jobs = frappe.db.sql(
		f"""
		select sum(case when {open_case} then 1 else 0 end) as open_cnt
		from `tabJob Opening` o
		where {jo_where}
		""",
		jo_params,
	)[0][0] or 0

	next_step_field = "null"
	group_fields = "a.status"
	if frappe.db.has_column("Job Applicant", "custom_suggested_next_step"):
		next_step_field = "a.custom_suggested_next_step"
		group_fields = "a.status, a.custom_suggested_next_step"

	pipeline_filters = list(app_filters)
	if frappe.db.has_column("Employee", "job_applicant"):
		pipeline_filters.append(
			"a.name not in (select job_applicant from `tabEmployee` where job_applicant is not null and job_applicant != '')"
		)
	pipeline_where = " and ".join(pipeline_filters)

	pipeline_rows = frappe.db.sql(
		f"""
		select a.status as status, {next_step_field} as next_step, count(*) as cnt
		from `tabJob Applicant` a
		where {pipeline_where}
		group by {group_fields}
		""",
		app_params,
		as_dict=True,
	)

	stage_counts = {stage: 0 for stage in PIPELINE_STAGES}
	for row in pipeline_rows:
		stage = _map_stage(row.get("status"), row.get("next_step"))
		if stage in stage_counts:
			stage_counts[stage] += int(row.get("cnt") or 0)

	if frappe.db.has_column("Employee", "job_applicant"):
		employee_count = frappe.db.sql(
			f"""
			select count(distinct e.job_applicant) as cnt
			from `tabEmployee` e
			left join `tabJob Applicant` a on a.name = e.job_applicant
			where e.job_applicant is not null
			  and e.job_applicant != ''
			  and e.docstatus < 2
			  and {app_where}
			""",
			app_params,
		)[0][0] or 0
		stage_counts["Nhân viên"] += int(employee_count or 0)

	stage_counts["Ứng viên"] = int(total_applicants or 0)
	pipeline = [{"stage": stage, "cnt": stage_counts[stage]} for stage in PIPELINE_STAGES]
	applicants = int(total_applicants or 0)

	sources = frappe.db.sql(
		f"""
		select ifnull(a.source,'N/A') as source, count(*) as cnt
		from `tabJob Applicant` a
		where {app_where}
		group by a.source
		order by cnt desc
		""",
		app_params,
		as_dict=True,
	)

	hired_filters = [
		"e.date_of_joining is not null",
		"e.date_of_joining between %(from_date)s and %(to_date)s",
	]
	hired_join = ""
	if pos or source:
		hired_join = "left join `tabJob Applicant` a on a.name = e.job_applicant"
		if pos:
			hired_filters.append("a.job_title = %(pos)s")
		if source:
			hired_filters.append("a.source = %(source)s")
	hired_where = " and ".join(hired_filters)

	monthly_hired = frappe.db.sql(
		f"""
		select month(e.date_of_joining) m, count(*) cnt
		from `tabEmployee` e
		{hired_join}
		where {hired_where}
		group by month(e.date_of_joining)
		""",
		app_params,
		as_dict=True,
	)

	left_filters = [
		"e.relieving_date is not null",
		"e.relieving_date between %(from_date)s and %(to_date)s",
	]
	left_join = ""
	if pos or source:
		left_join = "left join `tabJob Applicant` a on a.name = e.job_applicant"
		if pos:
			left_filters.append("a.job_title = %(pos)s")
		if source:
			left_filters.append("a.source = %(source)s")
	left_where = " and ".join(left_filters)

	monthly_left = frappe.db.sql(
		f"""
		select month(e.relieving_date) m, count(*) cnt
		from `tabEmployee` e
		{left_join}
		where {left_where}
		group by month(e.relieving_date)
		""",
		app_params,
		as_dict=True,
	)

	time_to_hire_filters = [
		"e.date_of_joining is not null",
		"e.date_of_joining between %(from_date)s and %(to_date)s",
		"e.job_applicant is not null",
	]
	if pos:
		time_to_hire_filters.append("a.job_title = %(pos)s")
	if source:
		time_to_hire_filters.append("a.source = %(source)s")
	time_to_hire_where = " and ".join(time_to_hire_filters)

	time_to_hire = frappe.db.sql(
		f"""
		select avg(datediff(e.date_of_joining, {jo_date_expr})) as avg_days
		from `tabEmployee` e
		left join `tabJob Applicant` a on a.name = e.job_applicant
		left join `tabJob Opening` o on o.name = a.job_title
		where {time_to_hire_where}
		""",
		app_params,
	)[0][0] or 0

	cost_field = _cost_field_expr()
	recruitment_cost = 0
	if cost_field:
		recruitment_cost = frappe.db.sql(
			f"""
			select sum(ifnull({cost_field}, 0)) as total_cost
			from `tabJob Opening` o
			where {jo_where}
			""",
			jo_params,
		)[0][0] or 0

	positions = frappe.db.sql(
		f"""
		select o.name as value, {_opening_label_expr()} as label
		from `tabJob Opening` o
		where {jo_date_expr} between %(from_date)s and %(to_date)s
		  and o.docstatus < 2
		order by o.modified desc
		""",
		params_base,
		as_dict=True,
	)

	if pos and not any(row.get("value") == pos for row in positions):
		extra_pos = frappe.db.sql(
			f"""
			select o.name as value, {_opening_label_expr()} as label
			from `tabJob Opening` o
			where o.name = %(pos)s
			""",
			{"pos": pos},
			as_dict=True,
		)
		positions = extra_pos + positions

	source_filters = [f"{app_date_expr} between %(from_date)s and %(to_date)s"]
	if pos:
		source_filters.append("a.job_title = %(pos)s")
	source_where = " and ".join(source_filters)
	source_params = dict(params_base)
	if pos:
		source_params["pos"] = pos

	source_rows = frappe.db.sql(
		f"""
		select distinct a.source as value
		from `tabJob Applicant` a
		where {source_where}
		  and ifnull(a.source, '') != ''
		order by a.source asc
		""",
		source_params,
		as_dict=True,
	)

	sources_options = [{"value": row["value"], "label": row["value"]} for row in source_rows]
	if source and not any(row.get("value") == source for row in sources_options):
		sources_options = [{"value": source, "label": source}] + sources_options

	return {
		"options": {
			"positions": positions,
			"sources": sources_options,
		},
		"kpis": {
			"open_jobs": int(open_jobs or 0),
			"applicants": int(applicants or 0),
			"time_to_hire_days": int(round(time_to_hire or 0)),
			"recruitment_cost": float(recruitment_cost or 0),
		},
		"pipeline": pipeline,
		"sources": sources,
		"monthly_hired": monthly_hired,
		"monthly_left": monthly_left,
		"turnover": _turnover_chart(monthly_hired, monthly_left),
	}


@frappe.whitelist()
def get_rejection_reasons(pos=None, source=None, from_date=None, to_date=None, limit=20):
	from_date, to_date = _date_range(from_date, to_date)
	params = {"from_date": from_date, "to_date": to_date}

	filters = [
		"fb.docstatus = 1",
		"fb.result in ('Rejected', 'Từ chối')",
		"date(fb.creation) between %(from_date)s and %(to_date)s",
	]

	if pos:
		filters.append("a.job_title = %(pos)s")
		params["pos"] = pos
	if source:
		filters.append("a.source = %(source)s")
		params["source"] = source

	reason_expr = _feedback_reason_expr()
	reason_sql = f"ifnull(nullif(trim({reason_expr}), ''), 'Không rõ')"

	try:
		limit_value = max(1, min(int(limit or 20), 50))
	except Exception:
		limit_value = 20

	params["limit_value"] = limit_value
	where_clause = " and ".join(filters)

	rows = frappe.db.sql(
		f"""
		select {reason_sql} as reason, count(*) as cnt
		from `tabInterview Feedback` fb
		left join `tabJob Applicant` a on a.name = fb.job_applicant
		where {where_clause}
		group by reason
		order by cnt desc
		limit %(limit_value)s
		""",
		params,
		as_dict=True,
	)

	return {
		"from_date": str(from_date),
		"to_date": str(to_date),
		"reasons": rows or [],
	}

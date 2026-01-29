import calendar
import unicodedata
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt


@frappe.whitelist()
def get_growth_dashboard_data(company=None, fiscal_year=None, month=None, data_type=None, docname=None):
	month_value = cint(month) or cint(frappe.utils.now_datetime().month)
	month_value = max(1, min(12, month_value))
	data_type = (data_type or "Actual").strip().lower()

	actual_doc = None
	plan_doc = None

	if docname:
		if data_type == "plan":
			plan_doc = frappe.get_doc("VNT Financial Plan Summary", docname)
		else:
			actual_doc = frappe.get_doc("VNT Financial Actual Summary", docname)

	if not actual_doc:
		actual_doc = _find_summary_doc("VNT Financial Actual Summary", company, fiscal_year)
	if not plan_doc:
		plan_doc = _find_summary_doc("VNT Financial Plan Summary", company, fiscal_year)

	if not actual_doc and not plan_doc:
		return _sample_payload(month_value)

	base_doc = actual_doc or plan_doc
	meta = {
		"month": month_value,
		"month_label": calendar.month_name[month_value],
		"company": getattr(base_doc, "company", None),
		"fiscal_year": getattr(base_doc, "fiscal_year", None),
		"actual_doc": getattr(actual_doc, "name", None) if actual_doc else None,
		"plan_doc": getattr(plan_doc, "name", None) if plan_doc else None,
	}

	actual_metrics = _build_metrics(actual_doc.lines, month_value) if actual_doc else None
	plan_metrics = _build_metrics(plan_doc.lines, month_value) if plan_doc else None

	return {
		"meta": meta,
		"actual": actual_metrics,
		"plan": plan_metrics,
	}


def _find_summary_doc(doctype, company, fiscal_year):
	filters = {}
	if company:
		filters["company"] = company
	if fiscal_year:
		filters["fiscal_year"] = fiscal_year
	name = frappe.get_value(doctype, filters, "name", order_by="modified desc")
	if not name:
		return None
	return frappe.get_doc(doctype, name)


def _build_metrics(lines, month):
	metrics = {
		"totals": {},
		"trends": {},
		"groups": [],
		"group1_items": [],
		"group2_items": [],
		"group3_items": [],
		"investment_breakdown": [],
		"cost_trend": [],
		"finance_breakdown": [],
	}

	if not lines:
		return metrics

	month = max(1, min(12, cint(month)))
	months = list(range(1, month + 1))
	metrics["trends"]["months"] = [f"T{m:02d}" for m in months]

	revenue_series = []
	profit_series = []
	cost_series = []
	for m in months:
		revenue_series.append(_sum_by_kind(lines, "doanh thu", m))
		profit_series.append(_sum_by_kind(lines, "loi nhuan", m))
		cost_series.append(_sum_by_kind(lines, "chi phi", m, group_key="nhom 4"))
	metrics["trends"]["revenue"] = revenue_series
	metrics["trends"]["profit"] = profit_series
	metrics["cost_trend"] = cost_series

	total_revenue_month = revenue_series[-1] if revenue_series else 0
	total_profit_month = profit_series[-1] if profit_series else 0
	total_revenue_ytd = sum(revenue_series)
	total_profit_ytd = sum(profit_series)
	total_revenue_prev = _sum_by_kind(lines, "doanh thu", month, prefix="prev")
	total_profit_prev = _sum_by_kind(lines, "loi nhuan", month, prefix="prev")
	metrics["totals"] = {
		"revenue_month": total_revenue_month,
		"profit_month": total_profit_month,
		"revenue_ytd": total_revenue_ytd,
		"profit_ytd": total_profit_ytd,
		"revenue_prev_month": _sum_by_kind(lines, "doanh thu", month - 1) if month > 1 else 0,
		"profit_prev_month": _sum_by_kind(lines, "loi nhuan", month - 1) if month > 1 else 0,
		"revenue_prev_ytd": total_revenue_prev,
		"profit_prev_ytd": total_profit_prev,
	}

	group_totals = defaultdict(lambda: defaultdict(float))
	group_details = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

	for line in lines:
		group = _normalize_group(getattr(line, "nhom_to", None))
		if not group:
			continue
		kind = _normalize(getattr(line, "khoan_muc", None))
		if kind not in ("doanh thu", "chi phi", "loi nhuan"):
			continue
		group_totals[group][f"{kind}_month"] += _value_for_month(line, "current", month)
		group_totals[group][f"{kind}_prev_month"] += _value_for_month(line, "current", month - 1)
		group_totals[group][f"{kind}_ytd"] += _sum_months(line, "current", month)
		group_totals[group][f"{kind}_prev_ytd"] += _sum_months(line, "prev", month)

		detail = _safe_text(getattr(line, "doi_tuong", None))
		group_details[group][detail][f"{kind}_ytd"] += _sum_months(line, "current", month)

	for group, values in group_totals.items():
		metrics["groups"].append(
			{
				"name": group.title(),
				"revenue_month": values.get("doanh thu_month", 0),
				"revenue_prev_month": values.get("doanh thu_prev_month", 0),
				"revenue_ytd": values.get("doanh thu_ytd", 0),
				"revenue_prev_ytd": values.get("doanh thu_prev_ytd", 0),
				"cost_month": values.get("chi phi_month", 0),
				"cost_prev_month": values.get("chi phi_prev_month", 0),
				"cost_ytd": values.get("chi phi_ytd", 0),
				"cost_prev_ytd": values.get("chi phi_prev_ytd", 0),
				"profit_month": values.get("loi nhuan_month", 0),
				"profit_prev_month": values.get("loi nhuan_prev_month", 0),
				"profit_ytd": values.get("loi nhuan_ytd", 0),
				"profit_prev_ytd": values.get("loi nhuan_prev_ytd", 0),
			}
		)

	metrics["groups"].sort(key=lambda row: row["name"])

	group1_items = _build_group_items(group_details.get("nhom 1", {}))
	group2_items = _build_group_items(group_details.get("nhom 2", {}))
	group3_items = _build_group_items(group_details.get("nhom 3", {}))
	metrics["group1_items"] = group1_items
	metrics["group2_items"] = group2_items
	metrics["group3_items"] = group3_items

	metrics["finance_breakdown"] = _filter_items(
		group1_items,
		["tài chính", "lai tien gui", "lãi tiền gửi", "adb", "lãi", "phí"],
	)
	metrics["investment_breakdown"] = _filter_items(
		group3_items,
		["co tuc", "cổ tức", "du phong", "dự phòng", "dau tu", "đầu tư"],
	)

	return metrics


def _build_group_items(items):
	records = []
	for name, values in items.items():
		if not name:
			continue
		records.append(
			{
				"name": name,
				"revenue_ytd": values.get("doanh thu_ytd", 0),
				"profit_ytd": values.get("loi nhuan_ytd", 0),
			}
		)
	records.sort(key=lambda row: row["revenue_ytd"], reverse=True)
	return records


def _filter_items(items, keywords):
	if not items:
		return []
	result = []
	for item in items:
		name = _normalize(item.get("name"))
		if any(keyword in name for keyword in keywords):
			result.append(item)
	return result or items[:4]


def _sum_by_kind(lines, kind, month, prefix="current", group_key=None):
	total = 0.0
	for line in lines:
		if group_key and _normalize_group(getattr(line, "nhom_to", None)) != group_key:
			continue
		if _normalize(getattr(line, "khoan_muc", None)) != kind:
			continue
		total += _value_for_month(line, prefix, month)
	return total


def _value_for_month(line, prefix, month):
	if month < 1:
		return 0.0
	field = f"{prefix}_t{month:02d}"
	return flt(getattr(line, field, 0) or 0)


def _sum_months(line, prefix, month):
	total = 0.0
	for m in range(1, month + 1):
		total += _value_for_month(line, prefix, m)
	return total


def _normalize_group(value):
	text = _normalize(value)
	if "nhom 1" in text:
		return "nhom 1"
	if "nhom 2" in text:
		return "nhom 2"
	if "nhom 3" in text:
		return "nhom 3"
	if "nhom 4" in text:
		return "nhom 4"
	return text or None


def _normalize(value):
	if not value:
		return ""
	text = str(value).strip().lower()
	text = unicodedata.normalize("NFD", text)
	text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
	return " ".join(text.split())


def _safe_text(value):
	return str(value).strip() if value else ""


def _sample_payload(month):
	months = list(range(1, month + 1))
	revenue = [120 + m * 5 for m in months]
	profit = [32 + m * 2 for m in months]
	cost = [80 + m * 4 for m in months]
	return {
		"meta": {"month": month, "month_label": calendar.month_name[month]},
		"actual": {
			"totals": {
				"revenue_month": revenue[-1],
				"profit_month": profit[-1],
				"revenue_ytd": sum(revenue),
				"profit_ytd": sum(profit),
				"revenue_prev_month": revenue[-2] if len(revenue) > 1 else 0,
				"profit_prev_month": profit[-2] if len(profit) > 1 else 0,
				"revenue_prev_ytd": sum(revenue) * 0.92,
				"profit_prev_ytd": sum(profit) * 0.9,
			},
			"trends": {"months": [f"T{m:02d}" for m in months], "revenue": revenue, "profit": profit},
			"groups": [
				{"name": "Nhóm 1", "profit_ytd": 220, "revenue_ytd": 520, "revenue_month": 70, "revenue_prev_month": 60, "cost_ytd": 300},
				{"name": "Nhóm 2", "profit_ytd": 140, "revenue_ytd": 260, "revenue_month": 32, "revenue_prev_month": 30, "cost_ytd": 120},
				{"name": "Nhóm 3", "profit_ytd": 110, "revenue_ytd": 190, "revenue_month": 25, "revenue_prev_month": 27, "cost_ytd": 80},
				{"name": "Nhóm 4", "profit_ytd": -160, "revenue_ytd": 0, "revenue_month": 0, "revenue_prev_month": 0, "cost_ytd": 160, "cost_month": cost[-1], "cost_prev_month": cost[-2] if len(cost) > 1 else 0},
			],
			"group1_items": [
				{"name": "Bán căn hộ", "revenue_ytd": 220, "profit_ytd": 60},
				{"name": "Cho thuê MMTB", "revenue_ytd": 150, "profit_ytd": 35},
				{"name": "Cho thuê VP", "revenue_ytd": 90, "profit_ytd": 22},
				{"name": "KD đồng phục", "revenue_ytd": 60, "profit_ytd": 15},
				{"name": "KD tài chính", "revenue_ytd": 40, "profit_ytd": 18},
				{"name": "Thoái vốn", "revenue_ytd": 20, "profit_ytd": 12},
			],
			"group2_items": [
				{"name": "Trung tâm PD&B", "revenue_ytd": 120, "profit_ytd": 30},
				{"name": "Vinatex Coats", "revenue_ytd": 80, "profit_ytd": 24},
			],
			"group3_items": [
				{"name": "Sợi Nam Định", "revenue_ytd": 70, "profit_ytd": 18},
				{"name": "Sợi Phú Cường", "revenue_ytd": 60, "profit_ytd": 16},
				{"name": "Đầu tư vốn vào ĐV khác", "revenue_ytd": 60, "profit_ytd": 25},
			],
			"investment_breakdown": [
				{"name": "Cổ tức", "profit_ytd": 36},
				{"name": "Dự phòng ĐTTC", "profit_ytd": -7},
				{"name": "Dự phòng khác", "profit_ytd": -4},
			],
			"finance_breakdown": [
				{"name": "Lãi tiền gửi", "profit_ytd": 12},
				{"name": "Lãi ADB", "profit_ytd": 4},
				{"name": "Phí quản lý", "profit_ytd": -2},
			],
			"cost_trend": cost,
		},
		"plan": None,
	}

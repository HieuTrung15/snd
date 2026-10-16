frappe.listview_settings["VNT Attendance Confirm"] = {
	onload(listview) {
		_setup_month_year_range_filter(listview);
		listview.page.add_inner_button(__("Cập nhật bất thường tháng này"), () => {
			frappe.call({
				method: "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm",
				freeze: true,
				freeze_message: __("Đang đối chiếu ca kế hoạch và dữ liệu chấm công..."),
				callback(response) {
					const result = response.message || {};
					frappe.msgprint({
						title: __("Kết quả cập nhật"),
						indicator: "green",
						message: [
							`${__("Số ngày bất thường")}: ${result["Số ngày bất thường"] || 0}`,
							`${__("Ngày làm việc về sớm")}: ${result["Ngày làm việc về sớm"] || 0}`,
							`${__("Số phiếu tạo mới")}: ${result["Số phiếu tạo mới"] || 0}`,
							`${__("Số phiếu cập nhật")}: ${result["Số phiếu cập nhật"] || 0}`,
						].join("<br>"),
					});
					listview.refresh();
				},
			});
		});
	},

	get_indicator(doc) {
		const colors = {
			"Chờ giải trình": "orange",
			"Chờ xác nhận": "blue",
			"Đã xác nhận": "green",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};


function _setup_month_year_range_filter(listview) {
	if (listview.__month_year_range_setup) return;
	listview.__month_year_range_setup = true;
	const original_get_filters_for_args = listview.get_filters_for_args.bind(listview);

	listview.get_filters_for_args = function () {
		const raw_filters = original_get_filters_for_args();
		const { month, year } = _extract_month_year(raw_filters, listview);
		const filters = raw_filters.filter((filter) =>
			filter[1] !== "month" && filter[1] !== "year"
		);
		const range = _compute_month_year_range(month, year);
		if (!range) return filters;
		_push_unique_filter(filters, listview.doctype, "from_date", "<=", range.end);
		_push_unique_filter(filters, listview.doctype, "to_date", ">=", range.start);
		return filters;
	};
}


function _extract_month_year(filters, listview) {
	let month = null;
	let year = null;
	(filters || []).forEach((filter) => {
		if (filter[1] === "month") month = filter[3];
		if (filter[1] === "year") year = filter[3];
	});
	const fields = listview?.page?.fields_dict;
	if (fields) {
		if (!month && fields.month) month = fields.month.get_value();
		if (!year && fields.year) year = fields.year.get_value();
	}
	return { month, year };
}


function _compute_month_year_range(month, year) {
	const parsed_month = parseInt(month, 10);
	const parsed_year = parseInt(year, 10);
	const has_month = Number.isFinite(parsed_month);
	const has_year = Number.isFinite(parsed_year);
	let start;
	let end;

	if (has_month && has_year) {
		if (parsed_month < 1 || parsed_month > 12) return null;
		start = new Date(parsed_year, parsed_month - 1, 1);
		end = new Date(parsed_year, parsed_month, 0);
	} else if (has_year) {
		start = new Date(parsed_year, 0, 1);
		end = new Date(parsed_year, 12, 0);
	} else if (has_month) {
		if (parsed_month < 1 || parsed_month > 12) return null;
		const current_year = new Date().getFullYear();
		start = new Date(current_year, parsed_month - 1, 1);
		end = new Date(current_year, parsed_month, 0);
	} else {
		return null;
	}
	return {
		start: frappe.datetime.obj_to_str(start),
		end: frappe.datetime.obj_to_str(end),
	};
}


function _push_unique_filter(filters, doctype, fieldname, condition, value) {
	const exists = (filters || []).some((filter) =>
		filter[0] === doctype
		&& filter[1] === fieldname
		&& filter[2] === condition
		&& filter[3] === value
	);
	if (!exists) filters.push([doctype, fieldname, condition, value]);
}

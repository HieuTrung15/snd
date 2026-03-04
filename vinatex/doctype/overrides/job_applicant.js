(() => {
	const OPENING_STATUSES = ["Open", "Đang đăng tuyển"];

	function apply_job_opening_query(frm) {
		const query = () => ({
			filters: [
				["Job Opening", "status", "in", OPENING_STATUSES],
				["Job Opening", "docstatus", "<", 2],
			],
		});
		frm.set_query("job_title", query);
		if (frm.fields_dict?.job_title) {
			frm.fields_dict.job_title.get_query = query;
		}
	}

	frappe.ui.form.on("Job Applicant", {
		setup(frm) {
			apply_job_opening_query(frm);
		},
		refresh(frm) {
			// HRMS sets status=Open in its refresh handler; run after it to override.
			setTimeout(() => apply_job_opening_query(frm), 0);
		},
		onload_post_render(frm) {
			setTimeout(() => apply_job_opening_query(frm), 0);
		},
	});
})();

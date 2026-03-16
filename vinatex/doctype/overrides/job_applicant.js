(() => {
	const OPENING_STATUSES = ["Open", "Đang đăng tuyển"];
	const MATCHED_STATUS = "Phù hợp";
	const HEADHUNTER_ROLE = "HR Headhunters";
	const SYSTEM_MANAGER_ROLE = "System Manager";
	const SPECIAL_RATING_MANAGER_USERS = [
		"thuhuyen@vinatex.com.vn",
		"thangnd@vinatex.com.vn",
	];
	const RATING_TABLE_FIELD = "custom_headhunter_ratings";

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

	function hasRole(role) {
		return (frappe.user_roles || []).includes(role);
	}

	function canManageAllRatings() {
		return (
			frappe.session.user === "Administrator" ||
			SPECIAL_RATING_MANAGER_USERS.includes(frappe.session.user) ||
			hasRole(SYSTEM_MANAGER_ROLE)
		);
	}

	function canEditOwnRating(frm) {
		return hasRole(HEADHUNTER_ROLE) && frm.doc.status === MATCHED_STATUS;
	}

	function applyRatingVisibility(frm) {
		frm.set_df_property("applicant_rating", "read_only", 1);

		const tableField = frm.get_field(RATING_TABLE_FIELD);
		if (!tableField || !tableField.grid) return;

		const canManageTable = canManageAllRatings();
		const canEditTable = canManageTable || canEditOwnRating(frm);
		frm.set_df_property(RATING_TABLE_FIELD, "read_only", canEditTable ? 0 : 1);
		frm.refresh_field(RATING_TABLE_FIELD);

		const grid = tableField.grid;
		grid.update_docfield_property("applicant_rating", "read_only", canEditTable ? 0 : 1);
		grid.update_docfield_property("headhunter", "read_only", canManageTable ? 0 : 1);
		grid.update_docfield_property("headhunter_full_name", "read_only", 1);
		grid.cannot_add_rows = !canManageTable;
		grid.can_delete_rows = canManageTable;
		grid.wrapper
			.find(".grid-add-row, .grid-add-multiple-rows, .grid-remove-rows, .grid-remove-all-rows")
			.toggle(canManageTable);
		grid.wrapper.find(".btn-open-row, .grid-edit-row").toggle(canEditTable);

		const onlySeeOwnRow = !canManageTable && hasRole(HEADHUNTER_ROLE);
		const currentUser = frappe.session.user;
		(grid.grid_rows || []).forEach((gridRow) => {
			const rowUser = gridRow?.doc?.headhunter;
			const visible = !onlySeeOwnRow || rowUser === currentUser;
			$(gridRow.wrapper).toggle(visible);
		});
	}

	frappe.ui.form.on("Job Applicant", {
		setup(frm) {
			apply_job_opening_query(frm);
		},
		refresh(frm) {
			// HRMS sets status=Open in its refresh handler; run after it to override.
			setTimeout(() => {
				apply_job_opening_query(frm);
				applyRatingVisibility(frm);
			}, 0);
		},
		status(frm) {
			applyRatingVisibility(frm);
		},
		onload_post_render(frm) {
			setTimeout(() => {
				apply_job_opening_query(frm);
				applyRatingVisibility(frm);
			}, 0);
		},
		custom_headhunter_ratings_on_form_rendered(frm) {
			applyRatingVisibility(frm);
		},
	});
})();

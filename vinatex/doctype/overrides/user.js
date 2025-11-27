(() => {
	const SETTINGS_FIELDS = [
		"desk_settings_section",
		"navigation_settings_section",
		"list_settings_section",
		"form_settings_section",
		"document_follow_notifications_section",
		"email_settings",
		"workspace_section",
		"app_section",
		"third_party_authentication",
		"sb2", // Defaults
		"sb3", // Security Settings
	];

	const keepFieldname = "change_password";
	console.log("[user.js] loaded", frappe.session?.user, frappe.boot?.site_name);
	function hide_field(frm, fieldname) {
		console.log("Hiding field:", fieldname);
		if (!frm.fields_dict) {
			return;
		}
		const field = frm.fields_dict[fieldname] || frm.get_field(fieldname);
		if (!field) {
			return;
		}

		frm.set_df_property(fieldname, "hidden", 1);

		const $wrapper = field.$wrapper || field.wrapper ? $(field.$wrapper || field.wrapper) : null;
		if ($wrapper) {
			$wrapper.closest(".form-section").addClass("hide-control").hide();
		}
	}

	function hide_settings_sections(frm) {
		if (frappe.user.has_role("System Manager")) {
			return;
		}

		SETTINGS_FIELDS.forEach((fieldname) => hide_field(frm, fieldname));

		// Extra safety: hide any section inside the Settings tab whose fieldname is not keepFieldname
		const settingsTab = frm.get_field("settings_tab");
		if (settingsTab && settingsTab.$wrapper) {
			settingsTab.$wrapper.find(".form-section").each((_, el) => {
				const fieldname = ($(el).attr("data-fieldname") || "").trim();
				if (fieldname && fieldname !== keepFieldname) {
					$(el).addClass("hide-control").hide();
				}
			});
		}
	}

	frappe.ui.form.on("User", {
		refresh(frm) {
			hide_settings_sections(frm);
			// Re-apply after any async refresh in case default scripts re-render
			setTimeout(() => hide_settings_sections(frm), 200);
		},
		onload_post_render(frm) {
			hide_settings_sections(frm);
		},
	});
})();

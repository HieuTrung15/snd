frappe.ui.form.on("Leave Application", {
	onload(frm) {
		// Ignore cancellation of doctype on cancel all.
		frm.ignore_doctypes_on_cancel_all = ["Leave Ledger Entry"];

		if (!frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}

        // tu lay ra nguoi duyet bat buoc
        // he thong da lay ra theo approver trong deparrtment
		// if (frm.doc.docstatus === 0) {
		// 	return frappe.call({
		// 		method: "hrms.hr.doctype.leave_application.leave_application.get_mandatory_approval",
		// 		args: {
		// 			doctype: frm.doc.doctype,
		// 		},
		// 		callback(r) {
        //             console.log(r.message);
		// 			if (!r.exc && r.message) {
		// 				frm.toggle_reqd("leave_approver", true);
		// 			}
		// 		},
		// 	});
		// }
	},

	// before_save(frm) {
	// 	get_approver(frm);
	// 	set_policy(frm);
	// },

	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Cancel"), function () {
				let dialog = new frappe.ui.Dialog({
					title: __("Bạn chắc chắn muốn hủy?"),
					primary_action_label: __("Xác nhận"),
					primary_action() {
						frappe.call({
							method: "cancel",
							doc: cur_frm.doc,
						});
						dialog.hide();
					},
				});
				dialog.show();
			}).removeClass().addClass("btn btn-warning");
		}

        // button de xem cac cong viec lien quan

		// frm.add_custom_button(__("Task"), function () {
		// 	frappe.set_route("List", "Task", { owner: frappe.session.user });
		// }, __("View related Documents"));
		// frm.add_custom_button(__("Timesheet"), function () {
		// 	frappe.set_route("List", "Timesheet", {
		// 		start_date: [">=", frm.doc.from_date],
		// 		end_date: ["<=", frm.doc.to_date],
		// 	});
		// }, __("View related Documents"));

		// choose_print_format(frm);
	},

	leave_type (frm) {
		// frm.set_value("task", "");
		// get_approver(frm);
		// set_policy(frm);

		// if (frm.doc.leave_type === "Work From Home") {
		// 	frm.trigger("get_task_list");
		// 	frm.trigger("set_mandatory");
		// 	frm.trigger("cal_extra_leave");
		// } else {
		// 	frm.trigger("calculate_total_days");
		// 	frm.set_df_property("task", "reqd", 0);
		// 	frm.refresh_field("task");
		// }

		frm.trigger("calculate_total_days");
		// frm.refresh_field("custom_leave_extra_day");
		// frm.refresh_field("leave_type_extra");
	},

	cal_extra_leave(frm) {
		const total_leave_days = Number(frm.doc.total_leave_days) || 0;
		const leave_balance = Number(frm.doc.leave_balance) || 0;

		if (frm.doc.leave_type === "Nghỉ phép năm" && total_leave_days > leave_balance) {
			if (leave_balance > 0) {
				frm.set_value("custom_leave_extra_day", total_leave_days - leave_balance);
			} else {
				frm.set_value("custom_leave_extra_day", total_leave_days);
			}
			frm.set_value("custom_leave_extra", "Nghỉ không lương");
			frm.refresh_field("custom_leave_extra_day");
			frm.refresh_field("custom_leave_extra");
			frm.refresh_field("custom_leave_application_details");
		} else {
			frm.set_value("custom_leave_extra_day", 0);
			frm.set_value("custom_leave_extra", "");
			frm.refresh_field("custom_leave_extra_day");
			frm.refresh_field("custom_leave_extra");
		}
	},

	get_leave_type(frm) {
		frm.set_value("custom_leave_application_details", "");

		const need_split =
			frm.doc.leave_type === "Nghỉ phép năm" &&
			Number(frm.doc.leave_balance) < Number(frm.doc.total_leave_days);

		if (need_split) {
			return frappe.call({
				method: "vinatex.vinatex.doctype.overrides.leave_application.get_leave_type",
				args: {
					employee: frm.doc.employee,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					half_day: frm.doc.half_day,
					half_day_date: frm.doc.half_day_date,
					leave_balance: frm.doc.leave_balance,
					extra_number: frm.doc.custom_leave_extra_day,
					total_leave_days: frm.doc.total_leave_days,
					status: frm.doc.status,
					leave_type_extra: frm.doc.custom_leave_extra,
					leave_type: frm.doc.leave_type,
				},
				async: false,
				callback(r) {
					if (r.message) {
						(r.message || []).forEach((s) => {
							let d = frappe.model.add_child(
								frm.doc,
								"Leave Application Type Item",
								"custom_leave_application_details"
							);
							d.from_date = s.from_date;
							d.to_date = s.to_date;
							d.total_days = s.total_days;
							d.half_day = s.half_day;
							d.half_day_date = s.half_day_date;
							d.leave_type = s.leave_type;
						});
						frm.refresh_field("custom_leave_application_details");
					}
				},
			});
		} else {
			frm.set_value("custom_leave_application_details", "");
			frm.refresh_field("custom_leave_application_details");
		}
	},

	// get_task_list(frm) {
	// 	frm.set_value("task", "");
	// 	return frappe.call({
	// 		method: "eupapp.eupapp.doctype.overrides.leave_application.get_task_list",
	// 		args: {
	// 			employee: frm.doc.employee,
	// 		},
	// 		async: false,
	// 		callback(r) {
	// 			if (r.message) {
	// 				(r.message || []).forEach((s) => {
	// 					let d = frappe.model.add_child(
	// 						frm.doc,
	// 						"Leave Application Item",
	// 						"task"
	// 					);
	// 					d.task = s.name;
	// 					d.old_progress = s.progress;
	// 					d.task_subject = s.subject;
	// 					d.project = s.project;
	// 					d.progress = (d.old_progress || 0) + (d.change || 0);
	// 				});
	// 				frm.refresh_field("task");
	// 			}
	// 		},
	// 	});
	// },

	custom_half_shift(frm) {
		set_datetime(frm);
		frm.refresh();
	},

	// set_mandatory(frm) {
	// 	return frappe.call({
	// 		method: "eupapp.eupapp.doctype.overrides.leave_application.get_checkin_type",
	// 		args: { employee: frm.doc.employee },
	// 		async: false,
	// 		callback(r) {
	// 			if (r.message) {
	// 				if (r.message !== "No Checkin No Confirm" && frm.doc.leave_type === "Work From Home") {
	// 					frm.set_df_property("task", "reqd", 1);
	// 					frm.refresh_field("task");
	// 				}
	// 			}
	// 		},
	// 	});
	// },

	// from_date(frm) {
	// 	get_approver(frm);
	// 	frm.trigger("make_dashboard");
	// 	frm.trigger("half_day_datepicker");
	// 	frm.trigger("calculate_total_days");
	// 	set_policy(frm);
	// 	set_datetime(frm);
	// },

	// to_date(frm) {
	// 	get_approver(frm);
	// 	frm.trigger("make_dashboard");
	// 	frm.trigger("half_day_datepicker");
	// 	frm.trigger("calculate_total_days");
	// 	set_policy(frm);
	// 	set_datetime(frm);
	// },

	// half_day_date(frm) {
	// 	get_approver(frm);
	// 	set_policy(frm);
	// 	frm.trigger("calculate_total_days");
	// 	frm.trigger("half_shift");
	// 	frm.trigger("validate_half_day_date");
	// 	set_datetime(frm);
	// },

	calculate_total_days(frm) {
		if (frm.doc.from_date && frm.doc.to_date && frm.doc.employee && frm.doc.leave_type) {
			const from_date = Date.parse(frm.doc.from_date);
			const to_date = Date.parse(frm.doc.to_date);

			if (to_date < from_date) {
				frappe.msgprint(__("To Date cannot be less than From Date"));
				frm.set_value("to_date", "");
				return;
			}

			// include holidays in leave days calculations
			return frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.get_number_of_leave_days",
				args: {
					employee: frm.doc.employee,
					leave_type: frm.doc.leave_type,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					half_day: frm.doc.half_day,
					half_day_date: frm.doc.half_day_date,
				},
				callback(r) {
					if (r && r.message) {
						frm.set_value("total_leave_days", r.message);
						// frm.trigger("get_leave_balance");
						frm.trigger("cal_extra_leave");
						frm.trigger("get_leave_type");
					}
				},
			});
		}
	},

	// validate_half_day_date(frm) {
	// 	let days = 0;
	// 	const details = (frm.doc.leave_type_details || []);
	// 	details.forEach((s) => {
	// 		if (frm.doc.half_day_date && frm.doc.half_day_date === s.half_day_date) {
	// 			days += 0.5;
	// 		}
	// 	});

	// 	if (days >= 1) {
	// 		frappe.throw(__("Please choose another half day date"));
	// 	}
	// },

	// add_task(frm) {
	// 	let dialog = new frappe.ui.Dialog({
	// 		title: __("Tạo nhiệm vụ tại nhà"),
	// 		fields: [
	// 			{
	// 				label: __("Subject"),
	// 				fieldname: "subject",
	// 				fieldtype: "Data",
	// 				reqd: 1,
	// 			},
	// 			{
	// 				label: __("Type"),
	// 				fieldname: "type",
	// 				fieldtype: "Link",
	// 				options: "Task Type",
	// 				default: "Operation Task",
	// 			},
	// 			{
	// 				label: __("Hours"),
	// 				fieldname: "hours",
	// 				fieldtype: "Float",
	// 				precision: 1,
	// 				reqd: 1,
	// 				default: 8,
	// 			},
	// 			{
	// 				label: __("Progress (%)"),
	// 				fieldname: "progress",
	// 				fieldtype: "Float",
	// 				precision: 1,
	// 				reqd: 1,
	// 				default: 100,
	// 			},
	// 			{
	// 				label: __("Allocated to"),
	// 				fieldname: "task_owner",
	// 				fieldtype: "Link",
	// 				options: "User",
	// 				reqd: 1,
	// 				default: frappe.session.user,
	// 			},
	// 			{ fieldname: "cb1", fieldtype: "Column Break" },
	// 			{
	// 				label: __("Task Description"),
	// 				fieldname: "description",
	// 				fieldtype: "Text Editor",
	// 				reqd: 0,
	// 			},
	// 		],
	// 		primary_action_label: __("Tạo mới"),
	// 		primary_action(values) {
	// 			frappe.call({
	// 				method: "eupapp.eupapp.doctype.overrides.leave_application.create_task",
	// 				args: { values },
	// 				freeze: true,
	// 				callback(r) {
	// 					if (r.message) {
	// 						dialog.hide();
	// 						frm.add_child("task", {
	// 							task: r.message.name,
	// 							task_subject: r.message.subject,
	// 							hours: r.message.hours,
	// 							change: r.message.progress,
	// 							progress: r.message.progress,
	// 							description: r.message.description,
	// 						});
	// 						frm.refresh_field("task");
	// 					} else {
	// 						dialog.hide();
	// 						frappe.msgprint({
	// 							title: "Error",
	// 							message: __("Tạo mới thất bại"),
	// 							indicator: "red",
	// 						});
	// 					}
	// 				},
	// 			});
	// 		},
	// 	});

	// 	setTimeout(function () {
	// 		const modalDialog = $(".modal-dialog");
	// 		modalDialog.css("max-width", "fit-content");
	// 	}, 500);

	// 	dialog.show();
	// },
});

frappe.ui.form.on("Leave Application Item", {
	// task_add(frm, cdt, cdn) {
	// 	const d = frappe.get_doc(cdt, cdn);
	// 	d.task = "";
	// 	frm.refresh_field("task");
	// 	frm.refresh_field("change");
	// 	frm.refresh_field("old_progress");
	// 	frm.refresh_field("progress");

	// 	if (frm.doc.parent_project) {
	// 		frappe.model.set_value(cdt, cdn, "project", frm.doc.parent_project);
	// 	}

	// 	// Set default linked value from NxDefault Link Value table
	// 	frappe.call({
	// 		method: "eupapp.eupapp.doctype.nxdefault_link_value.nxdefault_link_value.get_default_values",
	// 		args: { doctype: cdt },
	// 		callback(r) {
	// 			if (r.message) {
	// 				const data = r.message;
	// 				for (let i = 0; i < data.length; i++) {
	// 					let key = Object.keys(data[i]);
	// 					frappe.model.set_value(cdt, cdn, key[0], data[i][key[0]]);
	// 				}
	// 				frm.refresh_fields();
	// 			}
	// 		},
	// 	});
	// },

	// change(frm) {
	// 	(frm.doc.task || []).forEach((d) => {
	// 		let progress = (d.old_progress || 0) + (d.change || 0);
	// 		if (progress > 100) progress = 100;
	// 		if (progress < 0) progress = 0;
	// 		d.progress = progress;
	// 	});
	// 	frm.refresh_field("task");
	// },

	// task(frm, cdt, cdn) {
	// 	(frm.doc.task || []).forEach((d) => {
	// 		let progress = (d.old_progress || 0) + (d.change || 0);
	// 		if (progress > 100) progress = 100;
	// 		if (progress < 0) progress = 0;
	// 		d.progress = progress;
	// 	});
	// 	const row = frm.selected_doc;
	// 	if (row && row.task) {
	// 		frappe.db.get_value("Task", row.task, "project", (r) => {
	// 			frappe.model.set_value(cdt, cdn, "project", r.project);
	// 		});
	// 		frappe.db.get_value("Task", row.task, "progress", (r) => {
	// 			frappe.model.set_value(cdt, cdn, "old_progress", r.progress);
	// 		});
	// 	}
	// 	frm.refresh_field("task");
	// },

	// hours(frm, cdt, cdn) {
	// 	// Implement this server/client util on your side
	// 	// eslint-disable-next-line no-undef
	// 	calculate_end_time(frm, cdt, cdn);
	// },
});

// -----------------------------
// Helpers
// -----------------------------

// set employee (and company) to the one that's currently logged in
// const set_employee_and_company = function (frm) {
// 	const options = { user_id: frappe.session.user };
// 	const fields = ["name", "company"];
// 	frappe.db.get_value("Employee", options, fields).then(({ message }) => {
// 		if (message) {
// 			frm.set_value("employee", message.name);
// 			frm.set_value("company", message.company);
// 		}
// 	});
// };

function set_datetime(frm) {
	// frappe.call({
	// 	method: "vinatex.vinatex.doctype.overrides.leave_application.get_shift_type",
	// 	args: {
	// 		employee: frm.doc.employee,
	// 		from_date: frm.doc.from_date,
	// 		to_date: frm.doc.to_date,
	// 		half_day: frm.doc.half_day,
	// 		half_day_date: frm.doc.half_day_date,
	// 		half_shift: frm.doc.half_shift,
	// 	},
	// 	callback(r) {
	// 		if (r.message) {
	// 			frm.set_value("from_datetime", r.message["start_datetime"]);
	// 			frm.set_value("to_datetime", r.message["end_datetime"]);
	// 			frm.set_value("from_time", r.message["start_time"]);
	// 			frm.set_value("to_time", r.message["end_time"]);
	// 		}
	// 		frm.refresh_field("from_time");
	// 		frm.refresh_field("to_time");
	// 		frm.refresh_field("from_datetime");
	// 		frm.refresh_field("to_datetime");
	// 	},
	// });
    if (frm.doc.half_day && frm.doc.custom_half_shift === "First half of shift") {
        frm.set_value("custom_from_time", "08:00:00");
        frm.set_value("custom_to_time", "11:30:00");
    }
    else if (frm.doc.half_day && frm.doc.custom_half_shift === "Second half of shift") {
        frm.set_value("custom_from_time", "12:00:00");
        frm.set_value("custom_to_time", "17:00:00");
    }
    else {
        frm.set_value("custom_from_time", "");
        frm.set_value("custom_to_time", "");
    }
    frm.refresh();
}

// function set_project_in_timelog(frm) {
// 	if (frm.doc.parent_project) {
// 		(frm.doc.task || []).forEach((item) => {
// 			frappe.model.set_value(item.doctype, item.name, "project", frm.doc.parent_project);
// 		});
// 	}
// }

// function get_approver(frm) {
// 	frappe.call({
// 		method: "eupapp.eupapp.doctype.overrides.leave_application.get_approver",
// 		args: {
// 			docname: frm.doc.name,
// 			doctype: frm.doc.doctype,
// 			employee: frm.doc.employee,
// 			company: frm.doc.company,
// 			from_date: frm.doc.from_date,
// 			to_date: frm.doc.to_date,
// 			leave_type: frm.doc.leave_type,
// 			leave_approver: frm.doc.leave_approver,
// 		},
// 		callback(r) {
// 			if (r.message) {
// 				frm.clear_table("workflow");
// 				(r.message || []).forEach((s) => {
// 					frm.add_child("workflow", {
// 						user: s.user,
// 						designation: s.designation,
// 						state: s.state,
// 						all_approve: s.all_approve,
// 					});
// 				});
// 				frm.refresh_field("workflow");
// 			}
// 		},
// 	});
// }

// function set_policy(frm) {
// 	frappe.call({
// 		method: "eupapp.eupapp.doctype.overrides.leave_application.get_policy",
// 		args: {
// 			employee: frm.doc.employee,
// 			total_leave_days: frm.doc.total_leave_days,
// 			doctype: frm.doc.doctype,
// 			leave_type: frm.doc.leave_type,
// 			company: frm.doc.company,
// 			from_date: frm.doc.from_date,
// 			to_date: frm.doc.to_date,
// 		},
// 		callback(r) {
// 			if (r.message && r.message.length > 0) {
// 				frm.set_value("approval_policy", r.message[0].name);
// 			} else {
// 				frappe.show_alert({ message: __("Lack of policy"), indicator: "red" });
// 				frm.set_value("approval_policy", "");
// 			}
// 		},
// 	});
// }

// function choose_print_format(frm) {
// 	let meta = frappe.get_meta("Leave Application");
// 	meta.default_print_format = frm.doc.custom_print_format;
// 	frappe.meta.sync(meta);
// }
frappe.ui.form.on("Leave Application", {
	before_save (frm) {
		// Máy chủ sẽ submit ngay trong cùng giao dịch; các giá trị này giúp giao
		// diện phản ánh đúng trạng thái trước khi gửi dữ liệu.
		if (frm.is_new()) {
			frm.set_value("status", "Approved");
			if (frappe.meta.has_field(frm.doctype, "workflow_state")) {
				frm.set_value("workflow_state", "Đã duyệt");
			}
		}
	},
	
	// Override make_dashboard để hiển thị phép năm trước và năm nay riêng biệt
	make_dashboard(frm) {
		let leave_details = {};
		let lwps = [];

		if (frm.doc.employee) {
			frappe.call({
				method: "vinatex.vinatex.doctype.overrides.leave_application.get_leave_details_with_year",
				async: false,
				args: {
					employee: frm.doc.employee,
					date: frm.doc.from_date || frm.doc.posting_date,
					to_date: frm.doc.to_date || frm.doc.from_date || frm.doc.posting_date,
				},
				callback: function (r) {
					if (!r.exc && r.message) {
						if (r.message["leave_allocation"]) {
							leave_details = r.message["leave_allocation"];
						}
						if (r.message["lwps"]) {
							lwps = r.message["lwps"];
						}
					}
				},
				error: function(r) {
					console.error("Error fetching leave details:", r);
				}
			});

			$("div").remove(".form-dashboard-section.custom");

			frm.dashboard.add_section(
				frappe.render_template("leave_application_dashboard", {
					data: leave_details,
				}),
				__("Allocated Leaves"),
			);
			frm.dashboard.show();

			// Lấy danh sách leave types được phép (bao gồm cả tên gốc và tên có năm)
			let allowed_leave_types = Object.keys(leave_details || {});
			// Thêm tên gốc "Nghỉ phép năm" nếu có phép năm trước hoặc năm nay
			const has_annual_leave = allowed_leave_types.some(t => t.startsWith("Nghỉ phép năm"));
			if (has_annual_leave && !allowed_leave_types.includes("Nghỉ phép năm")) {
				allowed_leave_types.push("Nghỉ phép năm");
			}
			// lwps should be allowed for selection as they don't have any allocation
			allowed_leave_types = allowed_leave_types.concat(lwps || []);

			frm.set_query("leave_type", function () {
				return {
					filters: [["leave_type_name", "in", allowed_leave_types]],
				};
			});
		}
	},
	
	// Cập nhật dashboard khi thay đổi from_date
	from_date(frm) {
		if (frm.doc.employee) {
			frm.trigger("make_dashboard");
		}
	},
	
	// Cập nhật dashboard khi thay đổi to_date
	to_date(frm) {
		if (frm.doc.employee) {
			frm.trigger("make_dashboard");
		}
	},

	half_day(frm) {
		if (frm.doc.from_date && !frm.doc.to_date) {
			frm.set_value("to_date", frm.doc.from_date);
		}
	},
	employee (frm) {
		frm.trigger("make_dashboard");
	},

	onload(frm) {
		frm.set_value("follow_via_email", 0);
		// Ignore cancellation of doctype on cancel all.
		frm.ignore_doctypes_on_cancel_all = ["Leave Ledger Entry"];

		if (!frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}

	},

	refresh(frm) {
		[
			"custom_reject_reason",
			"custom_approver",
			"custom_approver_name",
			"leave_approver",
			"leave_approver_name",
			"custom_second_approver",
			"custom_second_approver_name",
		].forEach((fieldname) => frm.toggle_display(fieldname, false));

		frm.set_intro(
			__("Phiếu nghỉ sẽ được tự động duyệt và tạo chấm công ngay khi lưu."),
			"green"
		);

		if (frm.is_new()) {
			frm.set_value("custom_leave_group", "Nghỉ phép");
			frm.set_value("leave_type", "Nghỉ phép năm");
			// frappe.call({
            //     method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_reports_to",
            //     args: {
            //         user: frappe.session.user
            //     },
            //     callback: function (r) {
            //         if (r.message) {
            //             frm.set_value("custom_approver", r.message[0]);
            //             frm.set_value("custom_approver_name", r.message[1]);
            //         }
            //     }
            // });
		}
		// gỡ nút View Ledger (kể cả có group "View" hay không)
		frm.remove_custom_button(__('View Ledger'), __('View'));
		frm.remove_custom_button(__('View Ledger'));

		// nếu app khác add lại sau refresh, delay 1 nhịp để gỡ tiếp
		setTimeout(() => {
		frm.remove_custom_button(__('View Ledger'), __('View'));
		frm.remove_custom_button(__('View Ledger'));
		frm.remove_custom_button(__("Từ chối"));
		frm.remove_custom_button(__("Chuyển duyệt"));
		}, 0);

		// Hiển thị dashboard phép năm theo năm (override)
		if (frm.doc.docstatus === 0) {
			frm.trigger("make_dashboard");
		}

		// lọc leave_type theo custom_leave_group ngay khi mở form
    	set_leave_type_query(frm);
	},
	custom_leave_group(frm) {
			// đổi group thì reset leave_type & áp lại filter
			frm.set_value('leave_type', null);
			set_leave_type_query(frm);
	},

	leave_type (frm) {

		frm.trigger("calculate_total_days");
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
			frm.set_value("custom_leave_extra", "Nghỉ không hưởng lương");
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


	custom_half_shift(frm) {
		set_datetime(frm);
		frm.refresh();
	},


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
					if (r && r.message !== undefined && r.message !== null) {
						frm.set_value("total_leave_days", r.message);
						// frm.trigger("get_leave_balance");
						frm.trigger("cal_extra_leave");
						frm.trigger("get_leave_type");
					}
				},
			});
		}
	},
});


function set_datetime(frm) {
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

function set_leave_type_query(frm) {
  frm.set_query('leave_type', () => {
    if (!frm.doc.custom_leave_group) {
      // chưa chọn group → không cho chọn gì cả
      return { filters: { name: ['in', []] } };
      // hoặc: return { filters: [['name', 'in', []]] };
    }
    // đã chọn group → chỉ hiện Leave Type thuộc group đó
    return {
      filters: {
        custom_leave_group: frm.doc.custom_leave_group
      }
      // tương đương: filters: [['custom_leave_group', '=', frm.doc.custom_leave_group]]
    };
  });
}

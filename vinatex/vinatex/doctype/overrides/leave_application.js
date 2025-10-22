frappe.ui.form.on("Leave Application", {
	validate (frm) {
		// Khi chuyển về Rejected thì bắt buộc phải có lý do
		if (frm.doc.workflow_state === 'Rejected' && !frm.doc.custom_reject_reason) {
		frappe.throw(__('Vui lòng nhập "Lý do từ chối" trước khi từ chối.'));
		}
	},

	after_save (frm) {
		if (frm.is_new()) {
			frm.set_value("status", "Approved");
			frm.refresh_field("status");
		}
	},
	// lấy ra người duyệt cấp 2
	employee (frm) {
		if (frm.doc.total_leave_days > 3 && frm.doc.custom_designation_group == 'Chuyên viên, Nhân viên') {
			frappe.call({
			method: "vinatex.vinatex.doctype.overrides.leave_application.get_leave_approver_level_2",
			args: {
				employee: frm.doc.employee,
			},
			callback (r) {
				if (r.message) {
					frm.set_value("custom_second_approver", r.message);
				}}
			});
		}
	},
	// hiển thị người duyệt cấp 2 nếu nghỉ trên 3 ngày
	total_leave_days(frm) {
		if (frm.doc.total_leave_days > 3 && frm.doc.custom_designation_group == 'Chuyên viên, Nhân viên') {
			frappe.call({
			method: "vinatex.vinatex.doctype.overrides.leave_application.get_leave_approver_level_2",
			args: {
				employee: frm.doc.employee,
			},
			callback (r) {
				if (r.message) {
					frm.set_value("custom_second_approver", r.message);
				}}
			});
		}
	},

	onload(frm) {
		toggle_reject_reason(frm);
		frm.set_value("follow_via_email", 0);
		// Ignore cancellation of doctype on cancel all.
		frm.ignore_doctypes_on_cancel_all = ["Leave Ledger Entry"];

		if (!frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}

	},

	refresh(frm) {
		toggle_reject_reason(frm);
		// gỡ nút View Ledger (kể cả có group "View" hay không)
		frm.remove_custom_button(__('View Ledger'), __('View'));
		frm.remove_custom_button(__('View Ledger'));

		// nếu app khác add lại sau refresh, delay 1 nhịp để gỡ tiếp
		setTimeout(() => {
		frm.remove_custom_button(__('View Ledger'), __('View'));
		frm.remove_custom_button(__('View Ledger'));
		}, 0);

		// Ẩn luôn trong menu More Actions nếu có
		// frm.page.remove_menu_item(__('View Ledger'));
		// if (frm.doc.docstatus === 1) {
		// 	frm.add_custom_button(__("Cancel"), function () {
		// 		let dialog = new frappe.ui.Dialog({
		// 			title: __("Bạn chắc chắn muốn hủy?"),
		// 			primary_action_label: __("Xác nhận"),
		// 			primary_action() {
		// 				frappe.call({
		// 					method: "cancel",
		// 					doc: cur_frm.doc,
		// 				});
		// 				dialog.hide();
		// 			},
		// 		});
		// 		dialog.show();
		// 	}).removeClass().addClass("btn btn-warning");
		// }

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


function toggle_reject_reason(frm) {
  const isApprover =
    (frappe.user_roles || []).includes('Leave Approver L1') ||
    (frappe.user_roles || []).includes('Leave Approver L2');

  const pending = frm.doc.workflow_state === 'Chờ LĐ phòng/ban duyệt';
  const rejected = frm.doc.workflow_state === 'Từ chối';

  // Hiện cho người duyệt khi đang chờ duyệt (để điền), 
  // hoặc hiện cho tất cả khi đã Rejected (để xem lý do)
  const showForApproverToEdit = isApprover && pending;
  const showForEveryoneReadOnly = rejected;

  const shouldShow = showForApproverToEdit || showForEveryoneReadOnly;

  frm.toggle_display('custom_reject_reason', shouldShow);
  frm.set_df_property('custom_reject_reason', 'read_only', !showForApproverToEdit);
}

// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Meeting Room Booking", {
	after_save(frm) {
        // Chỉ auto chạy 1 lần khi còn ở state "Mới tạo"
        if (frm.doc.workflow_state === "Mới tạo") {
            frappe.call({
                method: "frappe.model.workflow.apply_workflow",
                args: {
                    doc: frm.doc,
                    action: "Chuyển duyệt", // action trong workflow
                },
                callback() {
                    frm.reload_doc();
                }
            });
        }
    },
	refresh(frm) {
		if (frm.is_new()) {
			frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
				.then(r => {
					if (r && r.message && r.message.name) {
						frm.set_value("employee", r.message.name);
					}
				});
			frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_meeting_room_booking.vnt_meeting_room_booking.get_reports_to",
                args: {
                    'user': frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("approver_name", r.message);
                    }
                }
            });
			frm.set_value("date", frappe.datetime.get_today());
		}
		// setFollowerByRoom(frm);
		// // frm.set_df_property("list_room", "read_only", 1);
		// loadTakenRooms(frm);
	},
	room_name(frm) {
		setFollowerByRoom(frm);
	},
	date(frm) {
		loadTakenRooms(frm);
	},
});
// nếu tầng 8 thì người theo dõi là Đỗ Thị Hiền 163
const setFollowerByRoom = (frm) => {
	if (!frm.doc) {
		return;
	}

	const follower = frm.doc.room_name === "Phòng họp tầng 8" ? "VGT00163" : "VGT00175";

	if (frm.doc.follower !== follower) {
		frm.set_value("follower", follower);
	}
};

const loadTakenRooms = (frm) => {
	if (!frm.doc || frm.doc.docstatus > 0) {
		return;
	}

	if (!frm.doc.date) {
		if (frm.doc.list_room && frm.doc.list_room.length) {
			frm.clear_table("list_room");
			frm.refresh_field("list_room");
			frm.doc.__unsaved = false;
		}
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_meeting_room_booking.vnt_meeting_room_booking.get_taken_rooms",
		args: {
			date: frm.doc.date,
	},
		callback(res) {
			frm.clear_table("list_room");
			(res.message || []).forEach((item) => {
				const row = frm.add_child("list_room", {
					date: item.date,
					room_name: item.room_name,
					start_time: item.start_time,
					end_time: item.end_time,
					employee: item.employee,
					employee_name: item.employee_name,
				});
				row.__islocal = false;
			});
			frm.refresh_field("list_room");
			frm.doc.__unsaved = false;
		},
	});
};

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
			frm.set_value("date", frappe.datetime.get_today());
		}
		refreshApprover(frm);
		refreshRoomAssignmentUI(frm);
	},
	employee(frm) {
		refreshApprover(frm);
	},
	room_name(frm) {
		setFollowerByRoom(frm);
	},
	date(frm) {
		loadTakenRooms(frm);
	},
});

const refreshApprover = (frm) => {
	if (!frm.doc.employee) {
		frm.set_value("approver", "");
		frm.set_value("approver_name", "");
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_meeting_room_booking.vnt_meeting_room_booking.get_reports_to",
		args: {
			employee: frm.doc.employee,
			user: frappe.session.user,
		},
		callback(res) {
			const approver = res && res.message ? res.message[0] : "";
			const approverName = res && res.message ? res.message[1] : "";
			frm.set_value("approver", approver || "");
			frm.set_value("approver_name", approverName || "");
		},
	});
};

// lấy người theo dõi theo cấu hình phòng họp
const setFollowerByRoom = (frm) => {
	if (!frm.doc) {
		return;
	}

	const roomName = frm.doc.room_name;
	if (!roomName) {
		if (frm.doc.follower || frm.doc.follower_name) {
			frm.set_value("follower", "");
			frm.set_value("follower_name", "");
		}
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_office_settings.vnt_office_settings.get_room_follower_info",
		args: {
			room_name: roomName,
		},
		callback(res) {
			const follower = res && res.message ? res.message.follower : "";
			const followerName = res && res.message ? res.message.follower_name : "";
			if (frm.doc.follower !== follower) {
				frm.set_value("follower", follower || "");
			}
			if (frm.doc.follower_name !== followerName) {
				frm.set_value("follower_name", followerName || "");
			}
		},
	});
};

const refreshRoomAssignmentUI = (frm) => {
	setTakenRoomsVisibility(frm, frm.is_new());
	frm.set_df_property("room_name", "read_only", 1);
	frm.refresh_field("room_name");

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_meeting_room_booking.vnt_meeting_room_booking.get_room_assignment_context",
		args: {
			user: frappe.session.user,
		},
		callback(res) {
			const canAssignRoom = Boolean(res && res.message && res.message.can_assign_room);
			frm.__can_assign_room = canAssignRoom;

			const showTakenRooms = shouldShowTakenRooms(frm);
			setTakenRoomsVisibility(frm, showTakenRooms);
			frm.set_df_property("room_name", "read_only", canAssignRoom ? 0 : 1);
			frm.refresh_field("room_name");

			if (showTakenRooms) {
				loadTakenRooms(frm);
				return;
			}

			clearTakenRooms(frm);
		},
	});
};

const shouldShowTakenRooms = (frm) => Boolean(frm.__can_assign_room) || frm.is_new();

const setTakenRoomsVisibility = (frm, isVisible) => {
	frm.toggle_display("section_break_gzd4", isVisible);
	frm.toggle_display("list_room", isVisible);
};

const clearTakenRooms = (frm) => {
	if (!frm.doc.list_room || !frm.doc.list_room.length) {
		return;
	}

	frm.clear_table("list_room");
	frm.refresh_field("list_room");
	frm.doc.__unsaved = false;
};

const loadTakenRooms = (frm) => {
	if (!frm.doc || frm.doc.docstatus > 0) {
		return;
	}

	if (!shouldShowTakenRooms(frm)) {
		clearTakenRooms(frm);
		return;
	}

	if (!frm.doc.date) {
		clearTakenRooms(frm);
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

from copy import deepcopy
from datetime import timedelta
from unittest import TestCase

from vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_policy import (
	build_backdated_employee_plan,
	make_preview_token,
)


def _request(**overrides):
	request = {
		"employees": ["EMP-001"],
		"target_shift_group": "1",
		"target_company": "Test Company",
		"effective_date": "2026-11-01",
		"membership_end_date": "2026-12-31",
		"generate_until": "2026-12-31",
		"note": "Approved backdated transfer",
		"today": "2026-11-05",
	}
	request.update(overrides)
	return request


def _schedule(name, weekday, shift_type, *, is_off=0):
	return {
		"name": name,
		"modified": "2026-10-01 08:00:00",
		"docstatus": 0,
		"shift_group": "1",
		"weekday": weekday,
		"shift_type": shift_type,
		"is_off": is_off,
	}


def _auto_assignment(work_date, *, name=None, shift_type="Sáng"):
	return {
		"name": name or f"ASG-{work_date}",
		"modified": "2026-11-01 00:00:00",
		"docstatus": 1,
		"employee": "EMP-001",
		"start_date": work_date,
		"end_date": work_date,
		"shift_type": shift_type,
		"status": "Active",
		"custom_assignment_source": "Kíp tự động",
		"custom_shift_group": "6",
		"custom_generated_by_shift_group": 1,
		"custom_schedule_date": work_date,
	}


def _snapshot(employee="EMP-001"):
	return {
		"employee": {
			"name": employee,
			"employee_name": f"Employee {employee}",
			"company": "Test Company",
			"status": "Active",
			"modified": "2026-11-01 00:00:00",
			"docstatus": 0,
		},
		"target_group": {
			"name": "1",
			"company": "Test Company",
			"disabled": 0,
			"effective_from": "2026-01-01",
			"effective_to": "2026-12-31",
			"modified": "2026-10-01 08:00:00",
			"docstatus": 0,
		},
		"schedules": [
			_schedule("SCH-SUN", "Sunday", "Sáng"),
			_schedule("SCH-MON", "Monday", "Chiều"),
			_schedule("SCH-TUE", "Tuesday", "Chiều"),
			_schedule("SCH-WED", "Wednesday", "Đêm"),
			_schedule("SCH-THU", "Thursday", "Đêm"),
			_schedule("SCH-FRI", "Friday", None, is_off=1),
			_schedule("SCH-SAT", "Saturday", "Sáng"),
		],
		"shift_types": [
			{
				"name": "Sáng",
				"start_time": "06:00:00",
				"end_time": "14:00:00",
				"modified": "2026-10-01 08:00:00",
				"docstatus": 0,
			},
			{
				"name": "Chiều",
				"start_time": "14:00:00",
				"end_time": "22:00:00",
				"modified": "2026-10-01 08:00:00",
				"docstatus": 0,
			},
			{
				"name": "Đêm",
				"start_time": "22:00:00",
				"end_time": "06:00:00",
				"modified": "2026-10-01 08:00:00",
				"docstatus": 0,
			},
		],
		"memberships": [
			{
				"name": "MEM-001",
				"employee": employee,
				"shift_group": "6",
				"company": "Test Company",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"status": "Active",
				"modified": "2026-10-01 08:00:00",
				"docstatus": 0,
			},
		],
		"assignments": [
			_auto_assignment("2026-11-01"),
			_auto_assignment("2026-11-02"),
			_auto_assignment("2026-11-03"),
			_auto_assignment("2026-11-04"),
		],
		"attendances": [],
		"checkins": [],
		"confirmations": [],
		"salary_slips": [],
	}


def _blocker_codes(plan):
	return {row["code"] for row in plan["blockers"]}


def _today_assignment_actions(plan, today="2026-11-05"):
	return [
		(row["action"], row["assignment"], row["target_shift_type"])
		for row in plan["assignment_actions"]
		if row["work_date"] == today
	]


def _snapshot_with_current_day_punch():
	snapshot = _snapshot()
	next(row for row in snapshot["schedules"] if row["weekday"] == "Thursday").update(
		shift_type="Sáng",
		is_off=0,
	)
	for shift_type in snapshot["shift_types"]:
		shift_type["determine_check_in_and_check_out"] = (
			"Strictly based on Log Type in Employee Checkin"
		)
	today_assignment = _auto_assignment("2026-11-05", shift_type="Sáng")
	today_assignment["custom_shift_group"] = "1"
	snapshot["assignments"].append(today_assignment)
	snapshot["checkins"] = [
		{
			"name": "CK-TODAY",
			"time": "2026-11-05 06:02:00",
			"log_type": "IN",
			"attendance": None,
			"shift_start": "2026-11-05 06:00:00",
			"modified": "2026-11-05 06:02:00",
			"docstatus": 0,
		}
	]
	return snapshot


class TestBackdatedShiftGroupTransferPolicy(TestCase):
	def test_current_day_checkin_is_preserved_when_exact_target_auto_assignment_exists(self):
		plan = build_backdated_employee_plan(
			_snapshot_with_current_day_punch(),
			_request(),
		)

		self.assertEqual(plan["status"], "READY")
		self.assertNotIn("CURRENT_WORK_DATE_DATA", _blocker_codes(plan))
		self.assertIn("CK-TODAY", plan["preserved_checkins"])
		self.assertNotIn(
			"2026-11-05",
			[row["work_date"] for row in plan["assignment_actions"]],
		)
		self.assertNotIn(
			"2026-11-05",
			[row["work_date"] for row in plan["attendance_actions"]],
		)

	def test_current_day_checkin_does_not_block_when_today_assignment_is_missing(self):
		snapshot = _snapshot_with_current_day_punch()
		snapshot["assignments"] = [
			row for row in snapshot["assignments"] if row["start_date"] != "2026-11-05"
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["status"], "READY")
		self.assertIn("CK-TODAY", plan["preserved_checkins"])
		self.assertEqual(
			_today_assignment_actions(plan),
			[("GENERATE_TARGET_AUTO", None, "Sáng")],
		)

	def test_current_day_checkin_rewrites_today_assignment_in_place(self):
		for fieldname, value in (("custom_shift_group", "6"), ("shift_type", "Chiều")):
			with self.subTest(fieldname=fieldname):
				snapshot = _snapshot_with_current_day_punch()
				snapshot["assignments"][-1][fieldname] = value

				plan = build_backdated_employee_plan(snapshot, _request())

				self.assertEqual(plan["status"], "READY")
				self.assertIn("CK-TODAY", plan["preserved_checkins"])
				self.assertEqual(
					_today_assignment_actions(plan),
					[("REWRITE_CURRENT_AUTO", "ASG-2026-11-05", "Sáng")],
				)

	def test_today_assignment_without_punch_is_also_rewritten_in_place(self):
		snapshot = _snapshot()
		snapshot["assignments"].append(_auto_assignment("2026-11-05", shift_type="Đêm"))

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["status"], "READY")
		self.assertEqual(
			_today_assignment_actions(plan),
			[("REWRITE_CURRENT_AUTO", "ASG-2026-11-05", "Đêm")],
		)

	def test_current_day_manual_assignment_still_blocks_as_manual(self):
		snapshot = _snapshot_with_current_day_punch()
		snapshot["assignments"][-1].update(
			custom_generated_by_shift_group=0,
			custom_assignment_source="Phân ca thủ công",
		)

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["status"], "BLOCKED")
		self.assertEqual(_blocker_codes(plan), {"MANUAL_SHIFT_ASSIGNMENT"})

	def test_current_day_checkin_on_target_off_day_cancels_today_assignment(self):
		snapshot = _snapshot_with_current_day_punch()
		snapshot["assignments"][-1]["custom_shift_group"] = "6"
		next(row for row in snapshot["schedules"] if row["weekday"] == "Thursday").update(
			shift_type=None,
			is_off=1,
		)
		snapshot["checkins"][0].update(
			time="2026-11-05 12:00:00",
			shift_start=None,
			modified="2026-11-05 12:00:00",
		)

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["status"], "READY")
		self.assertIn("CK-TODAY", plan["preserved_checkins"])
		self.assertEqual(
			_today_assignment_actions(plan),
			[("CANCEL_CURRENT_AUTO", "ASG-2026-11-05", None)],
		)

	def test_current_day_attendance_still_blocks_even_when_assignment_matches(self):
		snapshot = _snapshot_with_current_day_punch()
		snapshot["attendances"] = [
			{
				"name": "ATT-TODAY",
				"attendance_date": "2026-11-05",
				"shift": "Sáng",
				"status": "Present",
				"docstatus": 1,
				"modified": "2026-11-05 06:05:00",
				"custom_vnt_generated_by_pipeline": 1,
				"custom_vnt_source_shift_assignment": "ASG-2026-11-05",
			}
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["status"], "BLOCKED")
		self.assertIn("CURRENT_WORK_DATE_DATA", _blocker_codes(plan))

	def test_preview_reports_existing_target_membership_and_display_mismatch(self):
		snapshot = _snapshot()
		snapshot["employee"]["custom_shift_group"] = "4"
		snapshot["target_group"]["name"] = "3"
		snapshot["memberships"][0]["shift_group"] = "3"

		plan = build_backdated_employee_plan(
			snapshot,
			_request(target_shift_group="3"),
		)

		self.assertEqual(plan["membership_action"]["action"], "ALREADY_TARGET")
		self.assertEqual(plan["authoritative_shift_group"], "3")
		self.assertEqual(plan["display_shift_group"], "4")
		self.assertTrue(plan["display_mismatch"])

	def test_planner_is_not_hardcoded_to_one_employee(self):
		snapshot = _snapshot("EMP-999")
		for row in snapshot["assignments"]:
			row["employee"] = "EMP-999"
		plan = build_backdated_employee_plan(
			snapshot,
			_request(employees=["EMP-999"]),
		)

		self.assertEqual(plan["employee"], "EMP-999")
		self.assertEqual(plan["status"], "READY")

	def test_boundary_punch_linked_to_prior_attendance_is_preserved(self):
		snapshot = _snapshot()
		snapshot["attendances"].append(
			{
				"name": "ATT-OCT-31",
				"attendance_date": "2026-10-31",
				"shift": "Đêm",
				"status": "Present",
				"docstatus": 1,
				"modified": "2026-11-01 06:00:00",
			}
		)
		snapshot["checkins"].append(
			{
				"name": "CK-BOUNDARY",
				"time": "2026-11-01 05:59:29",
				"log_type": "IN",
				"attendance": "ATT-OCT-31",
				"shift_start": "2026-10-31 22:00:00",
				"modified": "2026-11-01 06:00:00",
				"docstatus": 0,
			}
		)

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["preserved_checkins"], ["CK-BOUNDARY"])
		self.assertNotIn("ATT-OCT-31", [row.get("attendance") for row in plan["attendance_actions"]])
		self.assertEqual(plan["status"], "READY")

	def test_previous_night_tail_today_is_eligible_for_previous_work_date(self):
		snapshot = _snapshot()
		snapshot["checkins"] = [
			{
				"name": "CK-NIGHT-IN",
				"time": "2026-11-04 21:55:39",
				"log_type": "IN",
				"attendance": None,
				"shift_start": "2026-11-04 22:00:00",
				"modified": "2026-11-04 21:55:39",
				"docstatus": 0,
			},
			{
				"name": "CK-NIGHT-OUT",
				"time": "2026-11-05 05:52:25",
				"log_type": "OUT",
				"attendance": None,
				"shift_start": "2026-11-04 22:00:00",
				"modified": "2026-11-05 05:52:25",
				"docstatus": 0,
			},
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["status"], "READY")
		self.assertNotIn("CURRENT_WORK_DATE_DATA", _blocker_codes(plan))
		self.assertIn(
			"2026-11-04",
			[row["work_date"] for row in plan["attendance_actions"]],
		)
		self.assertNotIn("CK-NIGHT-OUT", plan["preserved_checkins"])

	def test_unlinked_early_today_log_is_inferred_as_previous_night_tail(self):
		snapshot = _snapshot()
		snapshot["checkins"] = [
			{
				"name": "CK-OFFSHIFT-TAIL",
				"time": "2026-11-05 05:52:25",
				"log_type": "IN",
				"attendance": None,
				"shift_start": None,
				"offshift": 1,
				"modified": "2026-11-05 05:52:25",
				"docstatus": 0,
			}
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertNotIn("CURRENT_WORK_DATE_DATA", _blocker_codes(plan))
		self.assertEqual(plan["status"], "READY")

	def test_current_work_date_log_no_longer_blocks_execution(self):
		snapshot = _snapshot()
		next(row for row in snapshot["schedules"] if row["weekday"] == "Thursday").update(
			shift_type="Sáng",
			is_off=0,
		)
		for shift_type in snapshot["shift_types"]:
			shift_type["determine_check_in_and_check_out"] = (
				"Strictly based on Log Type in Employee Checkin"
			)
		snapshot["checkins"].append(
			{
				"name": "CK-TODAY",
				"time": "2026-11-05 06:02:00",
				"log_type": "IN",
				"attendance": None,
				"shift_start": "2026-11-05 06:00:00",
				"modified": "2026-11-05 06:02:00",
				"docstatus": 0,
			}
		)

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertNotIn("CURRENT_WORK_DATE_DATA", _blocker_codes(plan))
		self.assertEqual(plan["status"], "READY")
		self.assertIn("CK-TODAY", plan["preserved_checkins"])

	def test_current_day_log_uses_pipeline_ownership_not_previous_shift_buffer(self):
		snapshot = _snapshot()
		for shift_type in snapshot["shift_types"]:
			shift_type["determine_check_in_and_check_out"] = (
				"Strictly based on Log Type in Employee Checkin"
			)
			shift_type["allow_check_out_after_shift_end_time"] = 60
		next(row for row in snapshot["schedules"] if row["weekday"] == "Thursday").update(
			shift_type="Sáng",
			is_off=0,
		)
		snapshot["checkins"] = [
			{
				"name": "CK-TODAY-MORNING",
				"time": "2026-11-05 06:30:00",
				"log_type": "IN",
				"attendance": None,
				"shift_start": None,
				"modified": "2026-11-05 06:30:00",
				"docstatus": 0,
			}
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["status"], "READY")
		self.assertIn("CK-TODAY-MORNING", plan["preserved_checkins"])

	def test_pipeline_and_evidenced_legacy_attendance_are_rebuildable(self):
		for attendance in (
			{
				"name": "ATT-PIPELINE",
				"attendance_date": "2026-11-02",
				"shift": "Sáng",
				"status": "Absent",
				"docstatus": 1,
				"modified": "2026-11-02 22:00:00",
				"custom_vnt_generated_by_pipeline": 1,
				"custom_vnt_source_shift_assignment": "ASG-2026-11-02",
			},
			{
				"name": "ATT-LEGACY",
				"attendance_date": "2026-11-02",
				"shift": "Sáng",
				"status": "Absent",
				"docstatus": 1,
				"modified": "2026-11-02 22:00:00",
				"custom_vnt_generated_by_pipeline": 0,
				"custom_vnt_source_shift_assignment": None,
			},
		):
			with self.subTest(attendance=attendance["name"]):
				snapshot = _snapshot()
				snapshot["attendances"] = [attendance]
				snapshot["checkins"] = [
					{
						"name": "CK-LINKED",
						"time": "2026-11-02 14:03:00",
						"log_type": "IN",
						"attendance": attendance["name"],
						"shift_start": "2026-11-02 06:00:00",
						"modified": "2026-11-02 14:03:00",
						"docstatus": 0,
					}
				]
				plan = build_backdated_employee_plan(snapshot, _request())

				self.assertNotIn("AMBIGUOUS_LEGACY_ATTENDANCE", _blocker_codes(plan))
				self.assertIn(
					attendance["name"],
					[row.get("attendance") for row in plan["attendance_actions"]],
				)

	def test_legacy_absent_without_linked_checkin_is_blocked(self):
		snapshot = _snapshot()
		snapshot["attendances"] = [
			{
				"name": "ATT-LEGACY",
				"attendance_date": "2026-11-02",
				"shift": "Sáng",
				"status": "Absent",
				"docstatus": 1,
				"modified": "2026-11-02 22:00:00",
				"custom_vnt_generated_by_pipeline": 0,
				"custom_vnt_source_shift_assignment": None,
			}
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertIn("AMBIGUOUS_LEGACY_ATTENDANCE", _blocker_codes(plan))

	def test_multiple_active_attendance_on_one_date_is_blocked(self):
		snapshot = _snapshot()
		snapshot["attendances"] = [
			{
				"name": "ATT-LEAVE",
				"attendance_date": "2026-11-02",
				"shift": "Sáng",
				"status": "On Leave",
				"leave_type": "Annual Leave",
				"docstatus": 1,
			},
			{
				"name": "ATT-PIPELINE",
				"attendance_date": "2026-11-02",
				"shift": "Sáng",
				"status": "Absent",
				"custom_vnt_generated_by_pipeline": 1,
				"custom_vnt_source_shift_assignment": "ASG-2026-11-02",
				"docstatus": 1,
			},
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertIn("MULTIPLE_ACTIVE_ATTENDANCE", _blocker_codes(plan))
		self.assertIn("PROTECTED_ATTENDANCE_SOURCE", _blocker_codes(plan))

	def test_manual_assignment_is_blocked(self):
		snapshot = _snapshot()
		snapshot["assignments"][0].update(
			custom_generated_by_shift_group=0,
			custom_assignment_source="Phân ca thủ công",
		)

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertIn("MANUAL_SHIFT_ASSIGNMENT", _blocker_codes(plan))

	def test_target_off_cancels_historical_auto_assignment(self):
		snapshot = _snapshot()
		snapshot["schedules"][0].update(shift_type=None, is_off=1)

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertIn(
			{
				"action": "CANCEL_HISTORICAL_AUTO",
				"assignment": "ASG-2026-11-01",
				"work_date": "2026-11-01",
				"target_shift_type": None,
				"target_shift_group": "1",
			},
			plan["assignment_actions"],
		)

	def test_hc_sunday_policy_uses_default_shift_instead_of_target_off(self):
		snapshot = _snapshot()
		snapshot["employee"].update(
			department="Vào bông - NMSVNĐ",
			default_shift="Hành chính",
		)
		snapshot["target_group"]["name"] = "HC"
		snapshot["schedules"][0].update(shift_type=None, is_off=1)
		snapshot["shift_types"].append(
			{
				"name": "Hành chính",
				"start_time": "07:30:00",
				"end_time": "16:30:00",
				"modified": "2026-10-01 08:00:00",
				"docstatus": 0,
			}
		)

		plan = build_backdated_employee_plan(
			snapshot,
			_request(target_shift_group="HC"),
		)

		sunday_action = next(
			row for row in plan["assignment_actions"] if row["work_date"] == "2026-11-01"
		)
		self.assertEqual(sunday_action["action"], "REWRITE_HISTORICAL_AUTO")
		self.assertEqual(sunday_action["target_shift_type"], "Hành chính")

	def test_confirmed_explanation_is_blocked(self):
		snapshot = _snapshot()
		snapshot["confirmations"] = [
			{
				"name": "CONFIRM-ROW-1",
				"work_date": "2026-11-02",
				"hr_result": "Đồng ý",
				"modified": "2026-11-03 08:00:00",
				"docstatus": 0,
			}
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertIn("CONFIRMED_ATTENDANCE_EXPLANATION", _blocker_codes(plan))

	def test_submitted_salary_slip_is_blocked(self):
		snapshot = _snapshot()
		snapshot["salary_slips"] = [
			{
				"name": "SAL-001",
				"start_date": "2026-11-01",
				"end_date": "2026-11-30",
				"docstatus": 1,
				"modified": "2026-12-01 08:00:00",
			}
		]

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertIn("SUBMITTED_SALARY_SLIP", _blocker_codes(plan))

	def test_membership_end_before_today_is_blocked(self):
		plan = build_backdated_employee_plan(
			_snapshot(),
			_request(
				membership_end_date="2026-11-04",
				generate_until="2026-11-04",
			),
		)

		self.assertIn("MEMBERSHIP_END_BEFORE_TODAY", _blocker_codes(plan))

	def test_existing_target_membership_is_extended_to_requested_end(self):
		snapshot = _snapshot()
		snapshot["memberships"][0].update(
			shift_group="1",
			to_date="2026-11-30",
		)

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(plan["membership_action"]["action"], "EXTEND_TARGET")
		self.assertEqual(plan["membership_action"]["target_to_date"], "2026-12-31")

	def test_source_membership_starting_on_effective_date_is_inactivated(self):
		snapshot = _snapshot()
		snapshot["memberships"][0]["from_date"] = "2026-11-01"

		plan = build_backdated_employee_plan(snapshot, _request())

		self.assertEqual(
			plan["membership_action"]["action"],
			"INACTIVATE_SOURCE_CREATE_TARGET",
		)
		self.assertIsNone(plan["membership_action"]["source_end_date"])

	def test_batch_over_twenty_employees_is_blocked(self):
		plan = build_backdated_employee_plan(
			_snapshot(),
			_request(employees=[f"EMP-{index:03d}" for index in range(21)]),
		)

		self.assertIn("BATCH_LIMIT_EXCEEDED", _blocker_codes(plan))

	def test_preview_token_is_order_stable_and_changes_with_business_state(self):
		snapshot = _snapshot()
		reordered = deepcopy(snapshot)
		reordered["assignments"].reverse()
		original = make_preview_token(snapshot, _request())

		self.assertEqual(original, make_preview_token(reordered, _request()))

		changed = deepcopy(snapshot)
		changed["memberships"][0]["to_date"] = "2026-11-30"
		self.assertNotEqual(original, make_preview_token(changed, _request()))

	def test_preview_token_canonicalizes_mariadb_time_timedelta(self):
		snapshot = _snapshot()
		snapshot["shift_types"] = [
			{
				"name": "Sáng",
				"start_time": timedelta(hours=6),
				"end_time": timedelta(hours=14),
			}
		]

		original = make_preview_token(snapshot, _request())
		changed = deepcopy(snapshot)
		changed["shift_types"][0]["end_time"] = timedelta(hours=15)

		self.assertEqual(len(original), 64)
		self.assertNotEqual(original, make_preview_token(changed, _request()))

	def test_preview_token_changes_when_checkin_skip_flag_changes(self):
		snapshot = _snapshot()
		snapshot["checkins"] = [
			{
				"name": "CK-001",
				"time": "2026-11-02 14:03:00",
				"log_type": "IN",
				"skip_auto_attendance": 0,
			}
		]
		original = make_preview_token(snapshot, _request())
		snapshot["checkins"][0]["skip_auto_attendance"] = 1

		self.assertNotEqual(original, make_preview_token(snapshot, _request()))


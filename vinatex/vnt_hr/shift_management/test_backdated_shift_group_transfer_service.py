from copy import deepcopy
from contextlib import contextmanager, nullcontext
from datetime import date, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.vnt_hr.shift_management import shift_group_transfer_service as normal_service
from vinatex.vnt_hr.shift_management import (
	backdated_shift_group_transfer_service as backdated_service,
)
from vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_policy import (
	build_backdated_employee_plan,
	make_preview_token,
)
from vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service import (
	execute_backdated_shift_group_transfer,
	preview_backdated_shift_group_transfer,
)
from vinatex.vnt_hr.shift_management.constants import BACKDATED_TRANSFER_CONFIRMATION
from vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_policy import (
	_auto_assignment,
	_snapshot,
)


_preview = preview_backdated_shift_group_transfer.__wrapped__
_execute = execute_backdated_shift_group_transfer.__wrapped__


class _InMemoryDocument:
	def __init__(self, store, values, *, is_new=False):
		object.__setattr__(self, "store", store)
		object.__setattr__(self, "values", values)
		object.__setattr__(self, "is_new", is_new)
		object.__setattr__(self, "flags", SimpleNamespace(ignore_permissions=False))

	def __getattr__(self, name):
		return self.values.get(name)

	def __setattr__(self, name, value):
		if name in {"store", "values", "is_new", "flags"}:
			object.__setattr__(self, name, value)
		else:
			self.values[name] = value

	def get(self, name, default=None):
		return self.values.get(name, default)

	def as_dict(self):
		return deepcopy(self.values)

	def insert(self, ignore_permissions=False):
		doctype = self.values["doctype"]
		if not self.values.get("name"):
			self.values["name"] = f"NEW-{doctype}-{len(self.store.state.setdefault(doctype, {})) + 1}"
		self.store.state.setdefault(doctype, {})[self.values["name"]] = self.values
		return self

	def save(self, ignore_permissions=False):
		return self

	def submit(self):
		self.values["docstatus"] = 1
		return self

	def cancel(self):
		self.values["docstatus"] = 2
		if self.values["doctype"] == "Attendance":
			for checkin in self.store.state.get("Employee Checkin", {}).values():
				if checkin.get("attendance") == self.values["name"]:
					checkin["attendance"] = None
		if self.values["doctype"] == "Shift Assignment":
			self.values["status"] = "Inactive"
		return self


class _InMemoryDB:
	def __init__(self, store):
		self.store = store

	def set_value(self, doctype, name, fieldname, value=None, **kwargs):
		row = self.store.state[doctype][name]
		if isinstance(fieldname, dict):
			row.update(fieldname)
		else:
			row[fieldname] = value
		return row

	def count(self, doctype, filters=None):
		return sum(
			1
			for row in self.store.state.get(doctype, {}).values()
			if _row_matches(row, filters or {})
		)


class _InMemoryFrappe:
	ValidationError = frappe.ValidationError
	PermissionError = frappe.PermissionError

	def __init__(self, state):
		self.state = state
		self.db = _InMemoryDB(self)
		self.session = SimpleNamespace(user="Administrator")

	def get_doc(self, doctype_or_values, name=None):
		if isinstance(doctype_or_values, dict):
			values = deepcopy(doctype_or_values)
			values.setdefault("docstatus", 0)
			return _InMemoryDocument(self, values, is_new=True)
		return _InMemoryDocument(self, self.state[doctype_or_values][name])


def _comparable(value):
	if hasattr(value, "isoformat"):
		return value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
	return str(value) if value is not None else None


def _row_matches(row, filters):
	for fieldname, expected in filters.items():
		actual = row.get(fieldname)
		if isinstance(expected, (list, tuple)) and expected:
			operator = expected[0]
			operand = expected[1] if len(expected) > 1 else None
			if operator == "<" and not int(actual or 0) < int(operand):
				return False
			if operator == "between":
				start, end = operand
				if not (_comparable(start) <= _comparable(actual) <= _comparable(end)):
					return False
			if operator == "is" and operand == "set" and not actual:
				return False
		elif actual != expected:
			return False
	return True


def _reconciliation_fixture():
	snapshot = _snapshot()
	snapshot["employee"].update(
		custom_shift_group="6",
		custom_working_schedule_type="Theo kíp",
	)
	snapshot["attendances"] = [
		{
			"doctype": "Attendance",
			"name": "ATT-OCT-31",
			"employee": "EMP-001",
			"attendance_date": "2026-10-31",
			"shift": "Đêm",
			"status": "Present",
			"docstatus": 1,
			"modified": "2026-11-01 06:00:00",
		},
		{
			"doctype": "Attendance",
			"name": "ATT-NOV-02",
			"employee": "EMP-001",
			"attendance_date": "2026-11-02",
			"shift": "Sáng",
			"status": "Absent",
			"docstatus": 1,
			"modified": "2026-11-02 22:00:00",
			"custom_vnt_generated_by_pipeline": 1,
			"custom_vnt_source_shift_assignment": "ASG-2026-11-02",
		},
	]
	snapshot["checkins"] = [
		{
			"doctype": "Employee Checkin",
			"name": "CK-BOUNDARY",
			"employee": "EMP-001",
			"time": "2026-11-01 05:59:29",
			"log_type": "IN",
			"attendance": "ATT-OCT-31",
			"shift_start": "2026-10-31 22:00:00",
			"modified": "2026-11-01 06:00:00",
			"docstatus": 0,
		},
		{
			"doctype": "Employee Checkin",
			"name": "CK-NOV-02-IN",
			"employee": "EMP-001",
			"time": "2026-11-02 14:03:01",
			"log_type": "IN",
			"attendance": "ATT-NOV-02",
			"shift_start": "2026-11-02 06:00:00",
			"modified": "2026-11-02 14:03:01",
			"docstatus": 0,
		},
		{
			"doctype": "Employee Checkin",
			"name": "CK-NOV-02-OUT",
			"employee": "EMP-001",
			"time": "2026-11-02 21:54:04",
			"log_type": "OUT",
			"attendance": "ATT-NOV-02",
			"shift_start": "2026-11-02 06:00:00",
			"modified": "2026-11-02 21:54:04",
			"docstatus": 0,
		},
		{
			"doctype": "Employee Checkin",
			"name": "CK-NOV-04-IN",
			"employee": "EMP-001",
			"time": "2026-11-04 21:55:39",
			"log_type": "IN",
			"attendance": None,
			"shift_start": "2026-11-04 22:00:00",
			"modified": "2026-11-04 21:55:39",
			"docstatus": 0,
		},
		{
			"doctype": "Employee Checkin",
			"name": "CK-NOV-05-OUT",
			"employee": "EMP-001",
			"time": "2026-11-05 05:52:25",
			"log_type": "OUT",
			"attendance": None,
			"shift_start": "2026-11-04 22:00:00",
			"modified": "2026-11-05 05:52:25",
			"docstatus": 0,
		},
	]
	with patch.object(backdated_service, "today", return_value="2026-11-05"):
		request = backdated_service._normalize_backdated_request(**_preview_kwargs())
	plan = build_backdated_employee_plan(snapshot, request)
	state = {
		"Employee": {"EMP-001": deepcopy(snapshot["employee"])},
		"VNT Shift Group Assignment": {
			row["name"]: {"doctype": "VNT Shift Group Assignment", **deepcopy(row)}
			for row in snapshot["memberships"]
		},
		"Shift Assignment": {
			row["name"]: {"doctype": "Shift Assignment", **deepcopy(row)}
			for row in snapshot["assignments"]
		},
		"Attendance": {row["name"]: deepcopy(row) for row in snapshot["attendances"]},
		"Employee Checkin": {row["name"]: deepcopy(row) for row in snapshot["checkins"]},
		"Comment": {},
	}
	return snapshot, plan, request, _InMemoryFrappe(state)


def _today_punch_reconciliation_fixture():
	snapshot, _plan, request, fake = _reconciliation_fixture()
	today_assignment = _auto_assignment("2026-11-05", shift_type="Sáng")
	today_punch = {
		"doctype": "Employee Checkin",
		"name": "CK-TODAY",
		"employee": "EMP-001",
		"time": "2026-11-05 07:04:41",
		"log_type": "IN",
		"attendance": None,
		"shift": "Sáng",
		"shift_start": "2026-11-05 06:00:00",
		"modified": "2026-11-05 07:31:52",
		"docstatus": 0,
	}
	snapshot["assignments"].append(today_assignment)
	snapshot["checkins"].append(today_punch)
	fake.state["Shift Assignment"]["ASG-2026-11-05"] = {
		"doctype": "Shift Assignment",
		**deepcopy(today_assignment),
	}
	fake.state["Employee Checkin"]["CK-TODAY"] = deepcopy(today_punch)
	return snapshot, None, request, fake


def _run_reconciliation_fixture():
	return _run_reconciliation(*_reconciliation_fixture())


def _run_reconciliation(snapshot, plan, request, fake_frappe):
	events = {"generate": [], "process": [], "confirm": [], "sync": [], "resync": []}

	def generate(from_date, to_date, **kwargs):
		events["generate"].append((from_date, to_date, kwargs))
		return {"counts": {"CREATE": 2}}

	def process(from_date, to_date, **kwargs):
		events["process"].append((from_date, to_date, kwargs))
		attendance_state = fake_frappe.state["Attendance"]
		attendance_state["ATT-REBUILT-02"] = {
			"doctype": "Attendance",
			"name": "ATT-REBUILT-02",
			"employee": "EMP-001",
			"attendance_date": "2026-11-02",
			"shift": "Chiều",
			"status": "Present",
			"docstatus": 1,
		}
		attendance_state["ATT-REBUILT-04"] = {
			"doctype": "Attendance",
			"name": "ATT-REBUILT-04",
			"employee": "EMP-001",
			"attendance_date": "2026-11-04",
			"shift": "Đêm",
			"status": "Present",
			"docstatus": 1,
		}
		for name in ("CK-NOV-02-IN", "CK-NOV-02-OUT"):
			fake_frappe.state["Employee Checkin"][name]["attendance"] = "ATT-REBUILT-02"
		for name in ("CK-NOV-04-IN", "CK-NOV-05-OUT"):
			fake_frappe.state["Employee Checkin"][name]["attendance"] = "ATT-REBUILT-04"
		return {"Số Attendance tạo mới": 2}

	def confirm(**kwargs):
		events["confirm"].append(kwargs)
		return {"Số phiếu cập nhật": 1}

	def sync(employee_names, as_of_date=None):
		events["sync"].append((list(employee_names), as_of_date))
		fake_frappe.state["Employee"]["EMP-001"].update(
			custom_shift_group="1",
			custom_working_schedule_type="Theo kíp",
		)
		return {"counts": {"UPDATED": 1}}

	def resync(work_date, employee_names):
		events["resync"].append((work_date, list(employee_names), len(events["generate"])))
		return 1

	with patch.object(backdated_service, "frappe", fake_frappe), patch.object(
		backdated_service,
		"now_datetime",
		return_value="2026-11-05 08:00:00",
	), patch.object(
		backdated_service,
		"sync_checkin_shift_fields_for_date",
		side_effect=resync,
		create=True,
	), patch.object(
		backdated_service,
		"generate_shift_assignments",
		side_effect=generate,
		create=True,
	), patch.object(
		backdated_service,
		"process_attendance",
		side_effect=process,
		create=True,
	), patch.object(
		backdated_service,
		"make_attendance_confirm",
		side_effect=confirm,
		create=True,
	), patch.object(
		backdated_service,
		"sync_employee_current_shift_groups",
		side_effect=sync,
		create=True,
	):
		counts = backdated_service._apply_employee_reconciliation(
			snapshot,
			plan,
			request,
			"OP-001",
		)
	return snapshot, plan, request, fake_frappe, events, counts


def _preview_kwargs(employees=None):
	return {
		"employees": employees or ["EMP-001"],
		"target_shift_group": "1",
		"effective_date": "2026-11-01",
		"membership_end_date": "2026-12-31",
		"generate_until": "2026-12-31",
		"note": "Approved backdated transfer",
	}


def _fully_applied_snapshot():
	snapshot = _snapshot()
	snapshot["employee"].update(
		custom_shift_group="1",
		custom_working_schedule_type="Theo kíp",
	)
	snapshot["memberships"][0].update(shift_group="1", to_date="2026-12-31")
	snapshot["assignments"] = []
	shift_by_weekday = {
		0: "Chiều",
		1: "Chiều",
		2: "Đêm",
		3: "Đêm",
		5: "Sáng",
		6: "Sáng",
	}
	work_date = date(2026, 11, 1)
	assignment_by_date = {}
	while work_date <= date(2026, 12, 31):
		target_shift = shift_by_weekday.get(work_date.weekday())
		if target_shift:
			row = _auto_assignment(
				work_date.isoformat(),
				name=f"TARGET-{work_date}",
				shift_type=target_shift,
			)
			row["custom_shift_group"] = "1"
			snapshot["assignments"].append(row)
			assignment_by_date[work_date] = row
		work_date += timedelta(days=1)
	snapshot["attendances"] = []
	for work_date in (date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)):
		assignment = assignment_by_date[work_date]
		snapshot["attendances"].append(
			{
				"name": f"ATT-{work_date}",
				"employee": "EMP-001",
				"attendance_date": work_date.isoformat(),
				"shift": assignment["shift_type"],
				"status": "Present",
				"docstatus": 1,
				"custom_vnt_generated_by_pipeline": 1,
				"custom_vnt_source_shift_assignment": assignment["name"],
			}
		)
	snapshot["operation_audits"] = [
		{
			"name": "COMMENT-TRANSFER",
			"content": (
				'<pre>{"operation_id":"OP-DONE","summary":"Backdated Shift Group transfer completed",'
				'"before":{"request":{"employees":["EMP-001"],"target_shift_group":"1",'
				'"effective_date":"2026-11-01","membership_end_date":"2026-12-31",'
				'"generate_until":"2026-12-31","note":"Approved backdated transfer",'
				'"today":"2026-11-05"}}}</pre>'
			),
		}
	]
	return snapshot


class TestBackdatedShiftGroupTransferPreview(TestCase):
	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service._get_current_roles",
		return_value={"HR User"},
	)
	def test_preview_requires_manager_role(self, _roles):
		with self.assertRaises(frappe.PermissionError):
			_preview(**_preview_kwargs())

	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service._load_batch_snapshots"
	)
	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service._get_current_roles",
		return_value={"HR Manager"},
	)
	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service.today",
		return_value="2026-11-05",
	)
	def test_preview_returns_per_employee_actions_and_token(
		self, _today, _roles, load_snapshots
	):
		load_snapshots.return_value = {"EMP-001": _snapshot()}

		result = _preview(**_preview_kwargs())

		self.assertEqual(result["mode"], "BACKDATED")
		self.assertEqual(result["batch_status"], "READY")
		self.assertEqual(result["completed_through"], "2026-11-04")
		self.assertEqual(result["counts"]["READY"], 1)
		self.assertEqual(len(result["preview_token"]), 64)
		self.assertEqual(result["rows"][0]["employee"], "EMP-001")
		self.assertTrue(result["rows"][0]["attendance_actions"])
		self.assertTrue(result["rows"][0]["assignment_actions"])

	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service._load_batch_snapshots"
	)
	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service._get_current_roles",
		return_value={"System Manager"},
	)
	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service.today",
		return_value="2026-11-05",
	)
	def test_preview_is_read_only(self, _today, _roles, load_snapshots):
		snapshot = _snapshot()
		before = deepcopy(snapshot)
		load_snapshots.return_value = {"EMP-001": snapshot}

		_preview(**_preview_kwargs())

		self.assertEqual(snapshot, before)

	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service._load_batch_snapshots"
	)
	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service._get_current_roles",
		return_value={"HR Manager"},
	)
	@patch(
		"vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service.today",
		return_value="2026-11-05",
	)
	def test_preview_blocks_entire_batch_when_one_employee_is_unsafe(
		self, _today, _roles, load_snapshots
	):
		ready = _snapshot("EMP-001")
		blocked = _snapshot("EMP-002")
		for row in blocked["assignments"]:
			row["employee"] = "EMP-002"
		blocked["assignments"][0].update(
			custom_generated_by_shift_group=0,
			custom_assignment_source="Phân ca thủ công",
		)
		load_snapshots.return_value = {"EMP-001": ready, "EMP-002": blocked}

		result = _preview(
			**_preview_kwargs(["EMP-001", "EMP-002"])
		)

		self.assertEqual(result["batch_status"], "BLOCKED")
		self.assertFalse(result["can_execute"])
		self.assertEqual(result["counts"], {"BLOCKED": 1, "READY": 1})

	@patch.object(normal_service, "shift_management_schema_is_ready", return_value=True)
	def test_normal_transfer_still_rejects_backdate(self, _schema_ready):
		fake_frappe = SimpleNamespace(
			get_meta=lambda _doctype: SimpleNamespace(has_field=lambda _field: True),
			parse_json=frappe.parse_json,
			throw=lambda message, *args, **kwargs: (_ for _ in ()).throw(
				frappe.ValidationError(message)
			),
		)
		with patch.object(normal_service, "frappe", fake_frappe), patch.object(
			normal_service, "today", return_value="2026-11-05"
		), patch.object(normal_service, "_", side_effect=lambda value: value):
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"Bulk transfer cannot be backdated",
			):
				normal_service._validate_request(
					["EMP-001"],
					"1",
					"2026-11-01",
					"2026-12-31",
					"2026-12-31",
					"Approved future transfer",
				)

	@patch.object(backdated_service, "_require_employee_access")
	@patch.object(backdated_service.frappe, "get_meta")
	@patch.object(backdated_service.frappe, "get_all")
	def test_snapshot_projects_all_processing_inputs(
		self, get_all, get_meta, _require_access
	):
		calls = []
		get_meta.return_value = SimpleNamespace(has_field=lambda _field: True)

		def rows(doctype, **kwargs):
			calls.append((doctype, kwargs.get("fields") or []))
			if doctype == "Employee":
				return [
					frappe._dict(
						name="EMP-001",
						employee_name="Employee One",
						company="Test Company",
						status="Active",
						department="Production",
						default_shift="Sáng",
					)
				]
			if doctype == "VNT Shift Group":
				return [
					frappe._dict(
						name="1",
						company="Test Company",
						disabled=0,
						holiday_list="HL-GROUP",
					)
				]
			if doctype == "VNT Shift Group Schedule":
				return [
					frappe._dict(
						name="SCH-MON",
						shift_group="1",
						weekday="Monday",
						shift_type="Sáng",
						is_off=0,
					)
				]
			if doctype == "Shift Type":
				return [
					frappe._dict(
						name="Sáng",
						start_time="06:00:00",
						end_time="14:00:00",
						determine_check_in_and_check_out="Alternating entries as IN and OUT during the same shift",
					)
				]
			if doctype == "Company":
				return [
					frappe._dict(
						name="Test Company",
						default_holiday_list="HL-COMPANY",
					)
				]
			if doctype == "Holiday":
				return [
					frappe._dict(
						name="HOL-001",
						parent="HL-GROUP",
						holiday_date="2026-11-02",
						weekly_off=0,
						description="Holiday",
					)
				]
			return []

		get_all.side_effect = rows
		request = {
			"employees": ["EMP-001"],
			"target_shift_group": "1",
			"effective_date": date(2026, 11, 1),
			"membership_end_date": date(2026, 12, 31),
			"generate_until": date(2026, 12, 31),
			"today": date(2026, 11, 5),
		}

		snapshot = backdated_service._load_batch_snapshots(request)["EMP-001"]
		fields_by_doctype = {doctype: fields for doctype, fields in calls}

		self.assertIn("skip_auto_attendance", fields_by_doctype["Employee Checkin"])
		self.assertIn("department", fields_by_doctype["Employee"])
		self.assertIn(
			"determine_check_in_and_check_out",
			fields_by_doctype["Shift Type"],
		)
		self.assertEqual(snapshot["companies"][0]["default_holiday_list"], "HL-COMPANY")
		self.assertEqual(snapshot["holidays"][0]["name"], "HOL-001")


class TestBackdatedShiftGroupTransferExecutionSafety(TestCase):
	@patch.object(backdated_service, "_get_current_roles", return_value={"HR Manager"})
	def test_execute_requires_exact_confirmation(self, _roles):
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"XÁC NHẬN HỒI TỐ",
		):
			_execute(
				**_preview_kwargs(),
				preview_token="unused",
				confirmation_text="xac nhan",
			)

	@patch.object(backdated_service, "_execution_transaction")
	@patch.object(backdated_service, "_load_batch_snapshots")
	@patch.object(backdated_service, "_lock_backdated_dependencies")
	@patch.object(backdated_service, "_lock_employee_rows")
	@patch.object(backdated_service, "_get_current_roles", return_value={"HR Manager"})
	@patch.object(backdated_service, "today", return_value="2026-11-05")
	def test_execute_rejects_stale_token_before_write(
		self, _today, _roles, _lock, _lock_dependencies, load_snapshots, execution_transaction
	):
		load_snapshots.return_value = {"EMP-001": _snapshot()}

		with patch.object(
			backdated_service, "sync_employee_current_shift_groups"
		) as sync_cache, patch.object(
			backdated_service, "make_attendance_confirm"
		) as refresh_confirmation, self.assertRaisesRegex(
			frappe.ValidationError, "preview is stale"
		):
			_execute(
				**_preview_kwargs(),
				preview_token="stale-token",
				confirmation_text=BACKDATED_TRANSFER_CONFIRMATION,
			)

		execution_transaction.assert_not_called()
		sync_cache.assert_not_called()
		refresh_confirmation.assert_not_called()

	@patch.object(backdated_service, "_apply_employee_reconciliation")
	@patch.object(backdated_service, "_load_batch_snapshots")
	@patch.object(backdated_service, "_lock_backdated_dependencies")
	@patch.object(backdated_service, "_lock_employee_rows")
	@patch.object(backdated_service, "_get_current_roles", return_value={"System Manager"})
	@patch.object(backdated_service, "today", return_value="2026-11-05")
	def test_execute_locks_and_rechecks_batch(
		self, _today, _roles, lock_rows, lock_dependencies, load_snapshots, apply_employee
	):
		events = []
		snapshot = _snapshot()
		request = backdated_service._normalize_backdated_request(**_preview_kwargs())
		token = make_preview_token({"employees": [snapshot]}, request)
		lock_rows.side_effect = lambda employees: events.append(("lock", list(employees)))
		lock_dependencies.side_effect = lambda request: events.append(
			("lock_dependencies", request["target_shift_group"])
		)
		load_snapshots.side_effect = lambda _request: (
			events.append(("reload", None)) or {"EMP-001": snapshot}
		)
		apply_employee.side_effect = lambda *args, **kwargs: (
			events.append(("write", None)) or {"attendance_cancelled": 0}
		)

		with patch.object(
			backdated_service,
			"_execution_transaction",
			side_effect=lambda: nullcontext(),
		):
			result = _execute(
				**_preview_kwargs(),
				preview_token=token,
				confirmation_text=BACKDATED_TRANSFER_CONFIRMATION,
			)

		self.assertEqual(
			[event[0] for event in events],
			["lock", "lock_dependencies", "reload", "write"],
		)
		self.assertEqual(result["status"], "COMPLETED")

	@patch.object(backdated_service, "_apply_employee_reconciliation")
	@patch.object(backdated_service, "_load_batch_snapshots")
	@patch.object(backdated_service, "_lock_backdated_dependencies")
	@patch.object(backdated_service, "_lock_employee_rows")
	@patch.object(backdated_service, "_get_current_roles", return_value={"HR Manager"})
	@patch.object(backdated_service, "today", return_value="2026-11-05")
	def test_failure_rolls_back_all_employees(
		self, _today, _roles, _lock, _lock_dependencies, load_snapshots, apply_employee
	):
		first = _snapshot("EMP-001")
		second = _snapshot("EMP-002")
		for row in second["assignments"]:
			row["employee"] = "EMP-002"
		snapshots = {"EMP-001": first, "EMP-002": second}
		kwargs = _preview_kwargs(["EMP-001", "EMP-002"])
		request = backdated_service._normalize_backdated_request(**kwargs)
		token = make_preview_token({"employees": [first, second]}, request)
		load_snapshots.return_value = snapshots
		state = {
			"writes": [],
			"cache": {"EMP-001": "6", "EMP-002": "6"},
			"confirmations": ["CONF-UNCHANGED"],
		}
		original_state = deepcopy(state)

		@contextmanager
		def rollback_transaction():
			before = deepcopy(state)
			try:
				yield
			except Exception:
				state.clear()
				state.update(before)
				raise

		def apply(_snapshot_value, plan, *_args, **_kwargs):
			state["writes"].append(plan["employee"])
			state["cache"][plan["employee"]] = "1"
			state["confirmations"].append(f"CONF-{plan['employee']}")
			if plan["employee"] == "EMP-002":
				raise RuntimeError("second employee failed")
			return {}

		apply_employee.side_effect = apply
		with patch.object(
			backdated_service,
			"_execution_transaction",
			side_effect=rollback_transaction,
		):
			with self.assertRaisesRegex(RuntimeError, "second employee failed"):
				_execute(
					**kwargs,
					preview_token=token,
					confirmation_text=BACKDATED_TRANSFER_CONFIRMATION,
				)

		self.assertEqual(state, original_state)

	@patch.object(backdated_service, "_apply_employee_reconciliation")
	@patch.object(backdated_service, "_load_batch_snapshots")
	@patch.object(backdated_service, "_lock_backdated_dependencies")
	@patch.object(backdated_service, "_lock_employee_rows")
	@patch.object(backdated_service, "_get_current_roles", return_value={"HR Manager"})
	@patch.object(backdated_service, "today", return_value="2026-11-05")
	def test_second_execute_returns_already_applied(
		self, _today, _roles, _lock, _lock_dependencies, load_snapshots, apply_employee
	):
		snapshot = _fully_applied_snapshot()
		request = backdated_service._normalize_backdated_request(**_preview_kwargs())
		token = make_preview_token({"employees": [snapshot]}, request)
		load_snapshots.return_value = {"EMP-001": snapshot}

		result = _execute(
			**_preview_kwargs(),
			preview_token=token,
			confirmation_text=BACKDATED_TRANSFER_CONFIRMATION,
		)

		self.assertEqual(result["status"], "ALREADY_APPLIED")
		apply_employee.assert_not_called()

	def test_already_applied_rejects_missing_historical_attendance(self):
		snapshot = _fully_applied_snapshot()
		snapshot["attendances"] = []
		with patch.object(backdated_service, "today", return_value="2026-11-05"):
			request = backdated_service._normalize_backdated_request(**_preview_kwargs())
		plan = build_backdated_employee_plan(snapshot, request)

		self.assertFalse(
			backdated_service._batch_is_already_applied(
				{"EMP-001": snapshot},
				[plan],
				request,
			)
		)


class TestBackdatedShiftGroupTransferReconciliation(TestCase):
	def test_reconciliation_syncs_employee_cache_from_effective_membership(self):
		_snapshot_value, _plan, request, _fake, events, counts = (
			_run_reconciliation_fixture()
		)

		self.assertEqual(events["sync"], [(["EMP-001"], request["today"])])
		self.assertEqual(counts["employees_updated"], 1)

	def test_reconciliation_cancels_rebuilds_and_preserves_boundary_checkin(self):
		_snapshot_value, _plan, _request_value, fake, _events, counts = (
			_run_reconciliation_fixture()
		)

		self.assertEqual(fake.state["Attendance"]["ATT-NOV-02"]["docstatus"], 2)
		self.assertEqual(
			fake.state["Employee Checkin"]["CK-BOUNDARY"]["attendance"],
			"ATT-OCT-31",
		)
		self.assertEqual(
			fake.state["Employee Checkin"]["CK-NOV-02-IN"]["attendance"],
			"ATT-REBUILT-02",
		)
		self.assertEqual(counts["attendance_cancelled"], 1)

	def test_reconciliation_rewrites_historical_auto_assignment_with_audit(self):
		_snapshot_value, _plan, _request_value, fake, _events, _counts = (
			_run_reconciliation_fixture()
		)

		assignment = fake.state["Shift Assignment"]["ASG-2026-11-02"]
		self.assertEqual(assignment["shift_type"], "Chiều")
		self.assertEqual(assignment["custom_shift_group"], "1")
		comments = list(fake.state["Comment"].values())
		self.assertTrue(
			any(
				row["reference_name"] == "ASG-2026-11-02"
				and "OP-001" in row["content"]
				and "Sáng" in row["content"]
				for row in comments
			)
		)

	def test_cancel_historical_auto_assignment_marks_exact_guarded_row(self):
		snapshot, _plan, request, fake = _reconciliation_fixture()
		snapshot["schedules"][0].update(shift_type=None, is_off=1)
		plan = build_backdated_employee_plan(snapshot, request)
		action = next(
			row
			for row in plan["assignment_actions"]
			if row["work_date"] == "2026-11-01"
		)
		assignment = fake.get_doc("Shift Assignment", "ASG-2026-11-01")

		with patch.object(backdated_service, "frappe", fake), patch.object(
			backdated_service,
			"now_datetime",
			return_value="2026-11-05 08:00:00",
		):
			backdated_service._cancel_historical_auto_assignment(
				assignment,
				action,
				"OP-OFF",
			)

		self.assertEqual(
			fake.state["Shift Assignment"]["ASG-2026-11-01"]["docstatus"],
			2,
		)
		self.assertEqual(
			fake.state["Shift Assignment"]["ASG-2026-11-01"]["status"],
			"Inactive",
		)

	def test_reconciliation_closes_membership_updates_employee_and_generates(self):
		_snapshot_value, _plan, request, fake, events, counts = (
			_run_reconciliation_fixture()
		)

		self.assertEqual(
			fake.state["VNT Shift Group Assignment"]["MEM-001"]["to_date"],
			date(2026, 10, 31),
		)
		target_memberships = [
			row
			for name, row in fake.state["VNT Shift Group Assignment"].items()
			if name != "MEM-001"
		]
		self.assertEqual(len(target_memberships), 1)
		self.assertEqual(target_memberships[0]["shift_group"], "1")
		self.assertIn("OP-001", target_memberships[0]["note"])
		self.assertEqual(fake.state["Employee"]["EMP-001"]["custom_shift_group"], "1")
		self.assertEqual(
			fake.state["Employee"]["EMP-001"]["custom_working_schedule_type"],
			"Theo kíp",
		)
		self.assertEqual(events["generate"][0][0], request["effective_date"])
		self.assertEqual(events["generate"][0][1], request["generate_until"])
		self.assertEqual(counts["memberships_created"], 1)

	def test_confirmation_refresh_is_split_by_month(self):
		calls = []

		def refresh(**kwargs):
			calls.append((kwargs["from_date"], kwargs["to_date"], kwargs["employee"]))
			return {}

		with patch.object(
			backdated_service,
			"make_attendance_confirm",
			side_effect=refresh,
			create=True,
		):
			backdated_service._refresh_attendance_confirmations(
				"EMP-001",
				date(2026, 9, 30),
				date(2026, 11, 4),
			)

		self.assertEqual(
			calls,
			[
				(date(2026, 9, 1), date(2026, 9, 30), "EMP-001"),
				(date(2026, 10, 1), date(2026, 10, 31), "EMP-001"),
				(date(2026, 11, 1), date(2026, 11, 4), "EMP-001"),
			],
		)

	def test_membership_action_extends_existing_target_membership(self):
		snapshot, _plan, request, fake = _reconciliation_fixture()
		snapshot["memberships"][0].update(shift_group="1", to_date="2026-11-30")
		fake.state["VNT Shift Group Assignment"]["MEM-001"].update(
			shift_group="1",
			to_date="2026-11-30",
		)
		plan = build_backdated_employee_plan(snapshot, request)

		with patch.object(backdated_service, "frappe", fake):
			counts = backdated_service._apply_membership_action(
				snapshot, plan, request, "OP-EXTEND"
			)

		self.assertEqual(
			fake.state["VNT Shift Group Assignment"]["MEM-001"]["to_date"],
			date(2026, 12, 31),
		)
		self.assertEqual(counts["memberships_extended"], 1)

	def test_display_mismatch_target_membership_is_repaired_without_duplicate(self):
		snapshot, _plan, request, fake = _reconciliation_fixture()
		snapshot["employee"]["custom_shift_group"] = "4"
		snapshot["memberships"][0].update(shift_group="1", to_date="2026-12-31")
		fake.state["Employee"]["EMP-001"]["custom_shift_group"] = "4"
		fake.state["VNT Shift Group Assignment"]["MEM-001"].update(
			shift_group="1",
			to_date="2026-12-31",
		)
		plan = build_backdated_employee_plan(snapshot, request)
		before_names = set(fake.state["VNT Shift Group Assignment"])

		with patch.object(backdated_service, "frappe", fake):
			counts = backdated_service._apply_membership_action(
				snapshot, plan, request, "OP-ALREADY"
			)

		self.assertEqual(plan["membership_action"]["action"], "ALREADY_TARGET")
		self.assertEqual(counts, {})
		self.assertEqual(set(fake.state["VNT Shift Group Assignment"]), before_names)

	def test_membership_action_inactivates_same_day_source(self):
		snapshot, _plan, request, fake = _reconciliation_fixture()
		snapshot["memberships"][0]["from_date"] = "2026-11-01"
		fake.state["VNT Shift Group Assignment"]["MEM-001"]["from_date"] = "2026-11-01"
		plan = build_backdated_employee_plan(snapshot, request)

		with patch.object(backdated_service, "frappe", fake):
			counts = backdated_service._apply_membership_action(
				snapshot, plan, request, "OP-INACTIVATE"
			)

		self.assertEqual(
			fake.state["VNT Shift Group Assignment"]["MEM-001"]["status"],
			"Inactive",
		)
		self.assertEqual(counts["memberships_inactivated"], 1)
		self.assertEqual(counts["memberships_created"], 1)

	def test_reconciliation_processes_overnight_tail_but_not_today(self):
		_snapshot_value, _plan, request, fake, events, _counts = (
			_run_reconciliation_fixture()
		)

		self.assertEqual(events["process"][0][0], request["effective_date"])
		self.assertEqual(events["process"][0][1], date(2026, 11, 4))
		self.assertEqual(
			fake.state["Employee Checkin"]["CK-NOV-05-OUT"]["attendance"],
			"ATT-REBUILT-04",
		)
		self.assertNotIn(
			date(2026, 11, 5),
			[
				row.get("attendance_date")
				for row in fake.state["Attendance"].values()
			],
		)

	def test_reconciliation_rewrites_today_assignment_in_place_with_today_punch(self):
		snapshot, _plan, request, fake = _today_punch_reconciliation_fixture()
		plan = build_backdated_employee_plan(snapshot, request)

		_snapshot_value, _plan_value, _request_value, fake, _events, counts = (
			_run_reconciliation(snapshot, plan, request, fake)
		)

		self.assertEqual(plan["status"], "READY")
		assignment = fake.state["Shift Assignment"]["ASG-2026-11-05"]
		self.assertEqual(assignment["docstatus"], 1)
		self.assertEqual(assignment["status"], "Active")
		self.assertEqual(assignment["shift_type"], "Đêm")
		self.assertEqual(assignment["custom_shift_group"], "1")
		self.assertEqual(counts["current_assignments_rewritten"], 1)
		self.assertTrue(
			any(
				row["reference_name"] == "ASG-2026-11-05"
				and "Current-day automatic assignment rewritten" in row["content"]
				for row in fake.state["Comment"].values()
			)
		)
		self.assertIsNone(fake.state["Employee Checkin"]["CK-TODAY"]["attendance"])

	def test_reconciliation_cancels_today_assignment_for_target_off_day(self):
		snapshot, _plan, request, fake = _today_punch_reconciliation_fixture()
		next(row for row in snapshot["schedules"] if row["weekday"] == "Thursday").update(
			shift_type=None,
			is_off=1,
		)
		plan = build_backdated_employee_plan(snapshot, request)

		_snapshot_value, _plan_value, _request_value, fake, _events, counts = (
			_run_reconciliation(snapshot, plan, request, fake)
		)

		self.assertEqual(plan["status"], "READY")
		assignment = fake.state["Shift Assignment"]["ASG-2026-11-05"]
		self.assertEqual(assignment["docstatus"], 2)
		self.assertEqual(assignment["status"], "Inactive")
		self.assertEqual(counts["current_assignments_cancelled"], 1)

	def test_reconciliation_resyncs_today_checkins_after_generation(self):
		_snapshot_value, _plan, request, _fake, events, counts = (
			_run_reconciliation_fixture()
		)

		self.assertEqual(events["resync"], [(request["today"], ["EMP-001"], 1)])
		self.assertEqual(counts["current_day_checkins_resynced"], 1)

	def test_cancel_current_auto_is_never_already_applied(self):
		snapshot = _fully_applied_snapshot()
		next(row for row in snapshot["schedules"] if row["weekday"] == "Thursday").update(
			shift_type=None,
			is_off=1,
		)
		with patch.object(backdated_service, "today", return_value="2026-11-05"):
			request = backdated_service._normalize_backdated_request(**_preview_kwargs())
		plan = build_backdated_employee_plan(snapshot, request)

		self.assertIn(
			"CANCEL_CURRENT_AUTO",
			[row["action"] for row in plan["assignment_actions"]],
		)
		self.assertFalse(
			backdated_service._batch_is_already_applied(
				{"EMP-001": snapshot}, [plan], request
			)
		)

	@patch.object(backdated_service, "_apply_employee_reconciliation")
	@patch.object(backdated_service, "_load_batch_snapshots")
	@patch.object(backdated_service, "_lock_backdated_dependencies")
	@patch.object(backdated_service, "_lock_employee_rows")
	@patch.object(backdated_service, "_get_current_roles", return_value={"HR Manager"})
	@patch.object(backdated_service, "today", return_value="2026-11-05")
	def test_execute_manual_assignment_blocker_prevents_reconciliation(
		self, _today, _roles, _lock, _lock_dependencies, load_snapshots, apply_employee
	):
		snapshot = _snapshot()
		snapshot["assignments"][0].update(
			custom_generated_by_shift_group=0,
			custom_assignment_source="Phân ca thủ công",
		)
		request = backdated_service._normalize_backdated_request(**_preview_kwargs())
		token = make_preview_token({"employees": [snapshot]}, request)
		load_snapshots.return_value = {"EMP-001": snapshot}

		with self.assertRaisesRegex(frappe.ValidationError, "MANUAL_SHIFT_ASSIGNMENT"):
			_execute(
				**_preview_kwargs(),
				preview_token=token,
				confirmation_text=BACKDATED_TRANSFER_CONFIRMATION,
			)

		apply_employee.assert_not_called()


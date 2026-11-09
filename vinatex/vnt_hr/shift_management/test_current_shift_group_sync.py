from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe


class _Store:
	def __init__(self, *, employees=None, memberships=None, groups=None):
		self.employees = deepcopy(employees or {})
		self.memberships = [deepcopy(row) for row in (memberships or [])]
		self.groups = deepcopy({"HC": "2026"} if groups is None else groups)

	def get_all(self, doctype, filters=None, fields=None, order_by=None, pluck=None, **kwargs):
		if doctype == "Employee":
			names = list(self.employees)
			if filters and isinstance(filters.get("name"), (list, tuple)):
				names = [name for name in names if name in filters["name"][1]]
			if pluck == "name":
				return names
			return [frappe._dict({"name": name, **self.employees[name]}) for name in names]
		if doctype == "VNT Shift Group Assignment":
			rows = self.memberships
			if filters and filters.get("employee"):
				employee_filter = filters["employee"]
				allowed = employee_filter[1] if isinstance(employee_filter, (list, tuple)) else [employee_filter]
				rows = [row for row in rows if row["employee"] in allowed]
			return [frappe._dict(row) for row in rows]
		raise AssertionError(f"Unexpected doctype: {doctype}")

	def set_value(self, doctype, name, values, **kwargs):
		assert doctype == "Employee"
		self.employees[name].update(values)

	def get_value(self, doctype, name, fieldname, **kwargs):
		assert doctype == "VNT Shift Group"
		assert fieldname == "holiday_list"
		return self.groups.get(name)


def _membership(employee, group, from_date, to_date=None, name=None):
	return {
		"name": name or f"MEM-{employee}-{group}-{from_date}",
		"employee": employee,
		"shift_group": group,
		"from_date": from_date,
		"to_date": to_date,
		"status": "Active",
	}


class TestCurrentShiftGroupSync(TestCase):
	def _patch_store(self, store):
		from vinatex.vnt_hr.shift_management import current_shift_group_sync as sync

		fake_frappe = SimpleNamespace(
			get_all=store.get_all,
			db=SimpleNamespace(
				get_value=store.get_value,
				set_value=store.set_value,
			),
			ValidationError=frappe.ValidationError,
		)
		return patch.multiple(
			sync,
			frappe=fake_frappe,
			_=lambda value: value,
			_lock_employee_rows=lambda employee_names: None,
		)

	def test_resolve_active_shift_group_returns_exact_membership(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			resolve_active_shift_group,
		)

		store = _Store(
			employees={"EMP-001": {"custom_shift_group": "4"}},
			memberships=[_membership("EMP-001", "3", "2026-11-01", "2026-12-31")],
		)
		frappe_patch = self._patch_store(store)
		with frappe_patch:
			self.assertEqual(resolve_active_shift_group("EMP-001", "2026-11-05"), "3")

	def test_sync_preserves_legacy_cache_without_active_membership(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "Legacy",
					"custom_working_schedule_type": "Theo kíp",
				}
			}
		)
		frappe_patch = self._patch_store(store)
		with frappe_patch:
			result = sync_employee_current_shift_groups(["EMP-001"], "2026-11-05")

		self.assertEqual(result["counts"], {"SKIPPED_NO_ACTIVE_MEMBERSHIP": 1})
		self.assertEqual(store.employees["EMP-001"]["custom_shift_group"], "Legacy")

	def test_overlapping_active_memberships_raise_validation_error(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			resolve_active_shift_group,
		)

		store = _Store(
			employees={"EMP-001": {"custom_shift_group": "4"}},
			memberships=[
				_membership("EMP-001", "3", "2026-11-01", "2026-12-31", "MEM-3"),
				_membership("EMP-001", "4", "2026-11-01", "2026-12-31", "MEM-4"),
			],
		)
		frappe_patch = self._patch_store(store)
		with frappe_patch, self.assertRaises(frappe.ValidationError):
			resolve_active_shift_group("EMP-001", "2026-11-05")

	def test_sync_repairs_display_cache_to_active_target_membership(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "4",
					"custom_working_schedule_type": "Hành chính",
				}
			},
			memberships=[_membership("EMP-001", "3", "2026-11-01", "2026-12-31")],
		)
		frappe_patch = self._patch_store(store)
		with frappe_patch:
			result = sync_employee_current_shift_groups(["EMP-001"], "2026-11-05")

		self.assertEqual(result["counts"], {"UPDATED": 1})
		self.assertEqual(store.employees["EMP-001"]["custom_shift_group"], "3")
		self.assertEqual(
			store.employees["EMP-001"]["custom_working_schedule_type"],
			"Theo kíp",
		)

	def test_sync_hc_replaces_stale_employee_holiday_list_from_group_master(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "1",
					"custom_working_schedule_type": "Theo kíp",
					"holiday_list": "KIP-01-2026",
				}
			},
			memberships=[
				_membership("EMP-001", "HC", "2026-11-05", "2026-12-31")
			],
			groups={"HC": "2026"},
		)
		with self._patch_store(store):
			result = sync_employee_current_shift_groups(
				["EMP-001"], "2026-11-05"
			)

		self.assertEqual(result["counts"], {"UPDATED": 1})
		self.assertEqual(store.employees["EMP-001"]["custom_shift_group"], "HC")
		self.assertEqual(
			store.employees["EMP-001"]["custom_working_schedule_type"],
			"Hành chính",
		)
		self.assertEqual(store.employees["EMP-001"]["holiday_list"], "2026")

	def test_sync_hc_does_not_report_unchanged_when_only_holiday_list_is_stale(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "HC",
					"custom_working_schedule_type": "Hành chính",
					"holiday_list": "KIP-01-2026",
				}
			},
			memberships=[
				_membership("EMP-001", "HC", "2026-01-01", "2026-12-31")
			],
			groups={"HC": "2026"},
		)
		with self._patch_store(store):
			result = sync_employee_current_shift_groups(
				["EMP-001"], "2026-11-05"
			)

		self.assertEqual(result["counts"], {"UPDATED": 1})
		self.assertEqual(store.employees["EMP-001"]["holiday_list"], "2026")

	def test_sync_hc_without_holiday_list_raises_before_employee_update(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "1",
					"custom_working_schedule_type": "Theo kíp",
					"holiday_list": "KIP-01-2026",
				}
			},
			memberships=[
				_membership("EMP-001", "HC", "2026-11-05", "2026-12-31")
			],
			groups={"HC": None},
		)
		before = deepcopy(store.employees["EMP-001"])
		with self._patch_store(store), self.assertRaises(frappe.ValidationError):
			sync_employee_current_shift_groups(["EMP-001"], "2026-11-05")

		self.assertEqual(store.employees["EMP-001"], before)

	def test_sync_non_hc_preserves_employee_holiday_list(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "1",
					"custom_working_schedule_type": "Theo kíp",
					"holiday_list": "KIP-01-2026",
				}
			},
			memberships=[
				_membership("EMP-001", "3", "2026-11-05", "2026-12-31")
			],
			groups={"3": "KIP-03-2026"},
		)
		with self._patch_store(store):
			result = sync_employee_current_shift_groups(
				["EMP-001"], "2026-11-05"
			)

		self.assertEqual(result["counts"], {"UPDATED": 1})
		self.assertEqual(store.employees["EMP-001"]["custom_shift_group"], "3")
		self.assertEqual(
			store.employees["EMP-001"]["holiday_list"],
			"KIP-01-2026",
		)

	def test_sync_derives_admin_rotating_and_special_schedule_types(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-HC": {
					"custom_shift_group": "HC",
					"custom_working_schedule_type": "Theo kíp",
				},
				"EMP-ROTATING": {
					"custom_shift_group": "3",
					"custom_working_schedule_type": "Hành chính",
				},
				"EMP-SPECIAL": {
					"custom_shift_group": "ĐB HC-Đêm - Nghỉ T7",
					"custom_working_schedule_type": "Theo kíp",
				},
			},
			memberships=[
				_membership("EMP-HC", "HC", "2026-01-01", "2026-12-31"),
				_membership("EMP-ROTATING", "3", "2026-01-01", "2026-12-31"),
				_membership(
					"EMP-SPECIAL",
					"ĐB HC-Đêm - Nghỉ T7",
					"2026-01-01",
					"2026-12-31",
				),
			],
		)
		with self._patch_store(store):
			result = sync_employee_current_shift_groups(as_of_date="2026-11-05")

		self.assertEqual(result["counts"], {"UPDATED": 3})
		self.assertEqual(
			store.employees["EMP-HC"]["custom_working_schedule_type"],
			"Hành chính",
		)
		self.assertEqual(
			store.employees["EMP-ROTATING"]["custom_working_schedule_type"],
			"Theo kíp",
		)
		self.assertEqual(
			store.employees["EMP-SPECIAL"]["custom_working_schedule_type"],
			"Lịch đặc biệt",
		)

	def test_sync_locks_then_reloads_membership_before_updating_cache(self):
		from vinatex.vnt_hr.shift_management import current_shift_group_sync as sync

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "1",
					"custom_working_schedule_type": "Theo kíp",
				}
			},
			memberships=[
				_membership("EMP-001", "1", "2026-01-01", "2026-12-31")
			],
		)

		def concurrent_transfer_commits_while_waiting_for_lock(employee_names):
			self.assertEqual(employee_names, ["EMP-001"])
			store.memberships = [
				_membership("EMP-001", "3", "2026-11-05", "2026-12-31")
			]
			store.employees["EMP-001"].update(
				custom_shift_group="3",
				custom_working_schedule_type="Theo kíp",
			)

		with self._patch_store(store), patch.object(
			sync,
			"_lock_employee_rows",
			side_effect=concurrent_transfer_commits_while_waiting_for_lock,
			create=True,
		) as lock:
			result = sync.sync_employee_current_shift_groups(
				["EMP-001"], "2026-11-05"
			)

		lock.assert_called_once_with(["EMP-001"])
		self.assertEqual(result["counts"], {"UNCHANGED": 1})
		self.assertEqual(store.employees["EMP-001"]["custom_shift_group"], "3")

	def test_future_membership_changes_cache_only_on_effective_date(self):
		from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
			sync_employee_current_shift_groups,
		)

		store = _Store(
			employees={
				"EMP-001": {
					"custom_shift_group": "1",
					"custom_working_schedule_type": "Theo kíp",
				}
			},
			memberships=[
				_membership("EMP-001", "1", "2026-01-01", "2026-11-04", "MEM-1"),
				_membership("EMP-001", "3", "2026-11-05", "2026-12-31", "MEM-3"),
			],
		)
		frappe_patch = self._patch_store(store)
		with frappe_patch:
			before = sync_employee_current_shift_groups(["EMP-001"], "2026-11-04")
			on_date = sync_employee_current_shift_groups(["EMP-001"], "2026-11-05")

		self.assertEqual(before["counts"], {"UNCHANGED": 1})
		self.assertEqual(on_date["counts"], {"UPDATED": 1})
		self.assertEqual(store.employees["EMP-001"]["custom_shift_group"], "3")

	def test_normal_preview_reports_membership_as_authoritative_and_display_mismatch(self):
		from vinatex.vnt_hr.shift_management.shift_group_transfer_service import (
			_preview_employee,
		)

		employee = frappe._dict(
			name="EMP-001",
			employee_name="Employee One",
			company="Test Company",
			custom_shift_group="4",
			default_shift=None,
		)
		membership = frappe._dict(
			name="MEM-3",
			shift_group="3",
			from_date="2026-11-01",
			to_date="2026-12-31",
		)
		request = {
			"effective_date": frappe.utils.getdate("2026-11-05"),
			"membership_end_date": frappe.utils.getdate("2026-12-31"),
			"target_shift_group": "3",
			"target_company": "Test Company",
		}

		row = _preview_employee(
			employee,
			request,
			[membership],
			[],
			set(),
			set(),
			{"3", "4"},
		)

		self.assertEqual(row["authoritative_shift_group"], "3")
		self.assertEqual(row["display_shift_group"], "4")
		self.assertTrue(row["display_mismatch"])

	def test_normal_transfer_syncs_cache_after_successful_plan_change(self):
		from vinatex.vnt_hr.shift_management import shift_group_transfer_service as service

		request = {
			"employees": ["EMP-001"],
			"target_shift_group": "3",
			"target_company": "Test Company",
			"effective_date": frappe.utils.getdate("2026-11-05"),
			"membership_end_date": frappe.utils.getdate("2026-12-31"),
			"generate_until": frappe.utils.getdate("2026-12-31"),
			"note": "Approved transfer",
		}
		preview = {
			"assignment_names_to_cancel": [],
			"rows": [{"membership_action": "KEEP_MEMBERSHIP"}],
		}

		with patch.object(service, "_validate_request", return_value=request), patch.object(
			service, "_lock_employee_rows"
		), patch.object(service, "_build_preview", return_value=preview), patch.object(
			service, "_throw_if_blocked"
		), patch.object(service, "_apply_membership_change"), patch.object(
			service,
			"generate_shift_assignments",
			return_value={"counts": {"SKIP_EXISTING": 1}},
		), patch.object(service, "_assert_no_concurrent_usage"), patch.object(
			service,
			"sync_employee_current_shift_groups",
			return_value={"counts": {"UPDATED": 1}},
			create=True,
		) as sync, patch.object(service, "today", return_value="2026-11-05"):
			result = service._run_bulk_shift_group_transfer(request)

		sync.assert_called_once_with(
			["EMP-001"],
			frappe.utils.getdate("2026-11-05"),
		)
		self.assertEqual(result["employee_cache_counts"], {"UPDATED": 1})

	def test_daily_scheduler_syncs_cache_before_generating_assignments(self):
		from vinatex.vnt_hr.shift_management import scheduler

		events = []
		logger = SimpleNamespace(info=lambda *args, **kwargs: None)
		with patch.object(
			scheduler, "shift_management_schema_is_ready", return_value=True
		), patch.object(
			scheduler, "today", return_value="2026-11-05"
		), patch.object(
			scheduler,
			"sync_employee_current_shift_groups",
			side_effect=lambda: events.append("sync") or {"counts": {"UPDATED": 1}},
			create=True,
		), patch.object(
			scheduler,
			"generate_shift_assignments",
			side_effect=lambda *args, **kwargs: events.append("generate")
			or {"counts": {"CREATE": 1}},
		), patch.object(scheduler.frappe, "logger", return_value=logger):
			result = scheduler.run_daily_shift_assignment_generation()

		self.assertEqual(events, ["sync", "generate"])
		self.assertEqual(result["counts"], {"CREATE": 1})

	def test_daily_scheduler_does_not_generate_when_cache_sync_fails(self):
		from vinatex.vnt_hr.shift_management import scheduler

		logger = SimpleNamespace(info=lambda *args, **kwargs: None)
		with patch.object(
			scheduler, "shift_management_schema_is_ready", return_value=True
		), patch.object(
			scheduler, "today", return_value="2026-11-05"
		), patch.object(
			scheduler,
			"sync_employee_current_shift_groups",
			side_effect=frappe.ValidationError("overlap"),
			create=True,
		), patch.object(scheduler, "generate_shift_assignments") as generate, patch.object(
			scheduler.frappe, "logger", return_value=logger
		):
			with self.assertRaisesRegex(frappe.ValidationError, "overlap"):
				scheduler.run_daily_shift_assignment_generation()

		generate.assert_not_called()

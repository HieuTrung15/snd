# Presence-Only Administrative Departments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make completed Hành chính workdays for Vào bông and Công đoạn Đóng gói require only one IN and one OUT, while preserving existing rules everywhere else.

**Architecture:** Add a narrowly scoped department/shift policy predicate in the attendance-confirmation detector. For matching employees, evaluate the union of assigned and unplanned calendar-day Checkins by strict IN/OUT presence before the existing early/late/outside-shift branches; independently cap all confirmation ranges at the last completed site date.

**Tech Stack:** Python 3, Frappe Framework, MariaDB, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-05-presence-only-admin-departments-design.md`

## Global Constraints

- Exact Department names: `Vào bông - NMSVNĐ` and `Công đoạn Đóng gói - NMSVNĐ`.
- The policy applies only when `window.shift_type == "Hành chính"`.
- A complete day requires at least one `IN` and at least one `OUT`; no minimum duration applies.
- Never evaluate the current site date or a future date.
- Preserve OFF-day behavior and all behavior for other departments/shifts.
- Do not modify Employee Checkin or Attendance.
- Preserve confirmed attendance-confirmation rows as audit history.

## Review Focus

- An Employee moved into or out of a target Department before refresh must follow the current Employee.department value.
- An explicit range ending today or later must stop at yesterday and never inspect today's partial punches.
- An Hành chính day with rapid `IN` and `OUT` on a completed date must be accepted because no duration threshold exists.
- Blank, duplicate, or malformed log types must not fabricate the missing IN or OUT side.
- The same Department on a non-Hành chính planned shift must continue through the standard detector.

---

### Task 1: Exclude incomplete dates from confirmation processing

**Files:**
- Modify: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/vnt_attendance_confirm.py`
- Test: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/test_vnt_attendance_confirm.py`

**Interfaces:**
- Consumes: Frappe site-local `today()` and the existing `_resolve_date_range(from_date, to_date)` API.
- Produces: `_resolve_date_range(...) -> tuple[date, date]` whose `to_date` never exceeds yesterday.

- [ ] **Step 1: Write failing completed-date boundary tests**

Add `test_explicit_range_ending_today_is_capped_at_yesterday` with site today fixed at `2026-11-05`, input `2026-11-01..2026-11-05`, and expected range `2026-11-01..2026-11-04`. Add `test_range_containing_only_today_is_rejected` so no caller can process a partial day.

- [ ] **Step 2: Run tests and verify RED**

Run: `env PYTHONPATH=$PWD:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm -v`

Expected: FAIL because explicit ranges currently retain the current date.

- [ ] **Step 3: Cap `_resolve_date_range` at the last completed site date**

Use `getdate(today()) - timedelta(days=1)` for both explicit and default ranges before the existing order/month validation. Keep the returned `Đến ngày` truthful to the effective completed range.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 command. Expected: all attendance-confirmation tests pass.

- [ ] **Step 5: Commit**

Commit with message `fix: exclude incomplete attendance confirmation dates`.

### Task 2: Add the Department-specific IN/OUT presence policy

**Files:**
- Modify: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/vnt_attendance_confirm.py`
- Test: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/test_vnt_attendance_confirm.py`

**Interfaces:**
- Consumes: `employee.department`, `window.shift_type`, `planned_logs`, `outside_logs`, and existing issue payload codes.
- Produces: `_uses_presence_only_admin_policy(employee, window) -> bool`; extends `_detect_confirmation_issue(..., employee=None)` without changing default behavior for existing callers.

- [ ] **Step 1: Write failing policy and detector tests**

Add tests proving:
- both exact target Departments on Hành chính return `True` from the predicate;
- a moved Employee follows its current Department, and a target Department on another shift returns `False`;
- a completed rapid IN/OUT pair returns no issue;
- an IN/OUT pair wholly outside 07:30–16:30 returns no issue;
- no logs returns `WORKDAY_NO_CHECKIN`, IN-only returns `MISSING_OUT`, and OUT-only returns `MISSING_IN`;
- duplicate IN plus blank/malformed logs still returns `MISSING_OUT`;
- an OFF day with logs still returns `OFF_WITH_CHECKIN`;
- the existing standard Hành chính detector still reports `EARLY_EXIT` outside the two Departments.

- [ ] **Step 2: Run tests and verify RED**

Run the Task 1 command.

Expected: FAIL because the predicate and special detector path do not exist.

- [ ] **Step 3: Implement the presence-only policy**

Define the exact Department allow-list and `_uses_presence_only_admin_policy`. Pass the Employee row from `make_attendance_confirm` into `_detect_confirmation_issue`. After OFF/holiday checks and before standard inside/outside/early-exit logic, merge `planned_logs` and `outside_logs`, inspect normalized `log_type`, and emit only `WORKDAY_NO_CHECKIN`, `MISSING_IN`, `MISSING_OUT`, or no issue for the special policy.

- [ ] **Step 4: Run focused and neighboring tests**

Run: `env PYTHONPATH=$PWD:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm vinatex.vnt_hr.report.test_monthly_report_common 'vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.test_monthly_symbols' -v`

Expected: all tests pass with no changed behavior for other departments or monthly symbols.

- [ ] **Step 5: Commit**

Commit with message `feat: relax admin confirmation for two departments`.

### Task 3: Refresh historical unresolved confirmations safely

**Files:**
- No source changes; production operation after the implementation is integrated and deployed.

**Interfaces:**
- Consumes: `make_attendance_confirm` with exact Department filters and the existing empty-parent deletion/audit-preservation behavior.
- Produces: refreshed October and November 2026 unresolved rows for the ten currently active matching Employees.

- [ ] **Step 1: Back up and record the pre-refresh counts**

Create a site database backup. Query unresolved items for the two Departments grouped by `issue_code` and confirmation state; keep confirmed rows out of the deletion target.

- [ ] **Step 2: Run the completed-date refresh in monthly ranges**

Invoke `make_attendance_confirm` for each exact Department for `2026-10-01..2026-10-31` and `2026-11-01..2026-11-04`. Do not include `2026-11-05`.

- [ ] **Step 3: Verify production results**

Require that unresolved workday rows for matching Hành chính employees contain only `WORKDAY_NO_CHECKIN`, `MISSING_IN`, or `MISSING_OUT`; allow unchanged `OFF_WITH_CHECKIN` and confirmed historical rows. Verify zero empty non-cancelled parents and confirm Employee Checkin/Attendance counts and timestamps were not modified by this operation.

### Task 4: Whole-scope verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: fresh unit, neighboring-report, compile, diff, and production-query evidence.

- [ ] **Step 1: Run all named Python suites**

Run the Task 2 verification command. Expected: all tests pass.

- [ ] **Step 2: Compile and inspect the diff**

Run `python -m py_compile` for the modified Python/test files and `git diff --check`. Expected: exit 0 and only planned files changed after this plan's base.

- [ ] **Step 3: Request one final whole-branch review**

Review the completed branch against this plan/spec, the five Review Focus cases, and any rulings in the execution ledger before offering integration options.

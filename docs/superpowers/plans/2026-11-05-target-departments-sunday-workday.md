# Target Departments Sunday Workday Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat weekly Sundays as planned workdays for employees currently in Vào bông or Công đoạn Đóng gói, consistently across every consumer of the shared attendance classifier.

**Architecture:** Put the exact Department allow-list beside `classify_work_date` in the shared attendance-processing module. Preserve the existing early return for missing/explicit-OFF windows and ordinary holidays; only the `weekly_off = 1` branch changes. Existing confirmation, Attendance, report, and dashboard callers inherit the result without parallel rules.

**Tech Stack:** Python 3, Frappe Framework, MariaDB, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-05-target-departments-sunday-workday-design.md`

## Global Constraints

- Exact Departments: `Vào bông - NMSVNĐ` and `Công đoạn Đóng gói - NMSVNĐ`.
- Ignore only Holiday rows with `weekly_off = 1` when a non-OFF planned window exists.
- Preserve public/company holidays where `weekly_off = 0` and explicit OFF windows.
- Use current `Employee.department`; preserve other Departments unchanged.
- Do not modify Employee Checkin or Attendance during confirmation refresh.
- Do not process `2026-11-05` or later.
- Keep all source changes local on `develop`; do not commit or push.

## Review Focus

- A target Employee with a planned Hành chính window on Sunday is classified as `work`.
- A target Employee with an explicit OFF window on Sunday remains `off`.
- A target Employee on a non-weekly public holiday remains `holiday`.
- A non-target Employee on the same Sunday remains `off`.
- A target Employee moved out of the Department before refresh follows the new current Department and loses the exception.

---

### Task 1: Add the shared weekly-off Department policy

**Files:**
- Modify: `vinatex/vnt_hr/attendance_processing.py`
- Create: `vinatex/vnt_hr/shift_management/test_sunday_workday_policy.py`

**Interfaces:**
- Consumes: `classify_work_date(employee, window, holiday_context) -> str`, current `employee.department`, `window.is_off`, and Holiday `weekly_off`.
- Produces: `SUNDAY_WORKDAY_DEPARTMENTS` and shared `work` classification for the two exact Departments.

- [ ] **Step 1: Write failing classifier tests**

Add pure unit tests named `test_target_department_weekly_off_is_work`, `test_non_target_department_weekly_off_stays_off`, `test_target_department_public_holiday_stays_holiday`, `test_target_department_explicit_off_window_stays_off`, and `test_employee_moved_out_uses_current_department`.

- [ ] **Step 2: Run tests and verify RED**

Run: `env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_sunday_workday_policy -v`

Expected: target Department weekly-off cases fail because the shared classifier currently returns `off`.

- [ ] **Step 3: Implement the exact allow-list policy**

Define `SUNDAY_WORKDAY_DEPARTMENTS` in `attendance_processing.py`. In the existing `weekly_off` branch, return `work` when `employee.department` is in the allow-list; retain the earlier missing/explicit-OFF return and the existing Shift Group behavior for everyone else.

- [ ] **Step 4: Run focused and neighboring tests**

Run the Step 2 command, then run the attendance-confirmation and monthly-report suites from Task 2 of the prior plan.

Expected: all focused and neighboring tests pass.

- [ ] **Step 5: Leave changes local**

Record the diff and test evidence. Do not commit or push.

### Task 2: Refresh historical Sunday confirmations safely

**Files:**
- No source changes; production operation after Task 1 is active.

**Interfaces:**
- Consumes: shared Sunday classification and `make_attendance_confirm` with exact Department/month filters.
- Produces: reevaluated unresolved confirmations for `2026-10-01..2026-11-04`.

- [ ] **Step 1: Back up and capture pre-refresh state**

Create a site database backup. Record target Sunday issue counts and Checkin/Attendance counts plus fingerprints.

- [ ] **Step 2: Refresh both Departments by month**

Invoke `make_attendance_confirm` for both exact Departments over `2026-10-01..2026-10-31` and `2026-11-01..2026-11-04`.

- [ ] **Step 3: Verify production results**

Require zero unresolved target Sunday rows with `OFF_WITH_CHECKIN`; allow only the workday issue codes justified by strict IN/OUT evidence. Require zero current/future rows and empty parents, and unchanged Checkin/Attendance fingerprints.

### Task 3: Whole-scope verification and review

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: fresh unit, compile, diff, production-query, and independent review evidence.

- [ ] **Step 1: Run all named suites and compile modified Python files**

Run the focused policy, attendance-confirmation, and neighboring monthly-report suites; compile modified Python/test files.

- [ ] **Step 2: Inspect local `develop` state**

Run staged and unstaged `git diff --check`; require `HEAD == origin/develop` and no outgoing commits.

- [ ] **Step 3: Request one final whole-scope review**

Review the local diff against this plan/spec and the five Review Focus cases. Record findings and apply one TDD fix pass for Critical/Important findings only.

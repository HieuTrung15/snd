# Delete Empty Attendance Confirmations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete empty attendance-confirmation parents, report deletions, clean existing empty records, and prevent the state from recurring.

**Architecture:** Enforce the invariant at the reconciliation boundary in `_upsert_employee_confirmation`, where disappearing unresolved rows are already removed. Return a three-counter result to callers, expose deletion feedback in the list/form clients, and provide a narrow dry-run-capable repair function that deletes only non-cancelled parents with zero child rows through Frappe's document API.

**Tech Stack:** Python 3, Frappe Framework, JavaScript, Node built-in test runner, MariaDB.

**Spec:** `docs/superpowers/specs/2026-11-05-delete-empty-attendance-confirmations-design.md`

## Global Constraints

- Preserve confirmed child rows as audit history.
- Never delete a parent that has at least one child row.
- Do not modify Employee Checkin or Attendance.
- Use Frappe document deletion, not direct SQL deletes.
- Back up the site before deleting current production records.

## Review Focus

- Existing empty parent plus no current issue must be deleted once and counted once.
- Existing parent with a confirmed historical row plus no current issue must remain.
- Existing empty parent that gains a current issue must receive the row and remain.
- Refreshing the currently open document when it is deleted must route to the list without calling `reload_doc`.
- Dry-run cleanup must identify records without deleting any; live cleanup must delete exactly the identified names.

---

### Task 1: Enforce the empty-parent invariant during reconciliation

**Files:**
- Modify: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/vnt_attendance_confirm.py`
- Modify: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/test_vnt_attendance_confirm.py`

**Interfaces:**
- Consumes: existing `_upsert_employee_confirmation(employee, from_date, to_date, issues)` reconciliation behavior.
- Produces: `_upsert_employee_confirmation(...) -> tuple[int, int, int]` as `(created, updated, deleted)` and `make_attendance_confirm` result key `Số phiếu đã xóa`.

- [ ] **Step 1: Write failing tests**

Add tests proving: an existing parent is deleted after its final unresolved row disappears; a confirmed historical row remains; an existing empty parent that receives an issue is not deleted; no parent/no issues returns three zeros; and the public empty result includes `Số phiếu đã xóa: 0`.

- [ ] **Step 2: Run tests and verify RED**

Run: `env PYTHONPATH=$WORKTREE:$BENCH/apps/frappe:$BENCH/apps/erpnext:$BENCH/apps/hrms $BENCH/env/bin/python -m unittest vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm -v`

Expected: FAIL because the upsert still saves an empty parent, returns two counters, and the public result lacks the deletion counter.

- [ ] **Step 3: Implement the minimal backend change**

Delete an existing parent with `frappe.delete_doc(..., ignore_permissions=True)` whenever reconciliation leaves `items` empty, return the three counters from every branch, and aggregate `Số phiếu đã xóa` in `make_attendance_confirm`.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 command. Expected: all attendance-confirm tests pass.

- [ ] **Step 5: Commit**

Commit tests and implementation with message `fix: delete empty attendance confirmations`.

### Task 2: Report deletion correctly in the browser

**Files:**
- Modify: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/vnt_attendance_confirm_list.js`
- Modify: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/vnt_attendance_confirm.js`
- Create: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/test_vnt_attendance_confirm_ui.js`

**Interfaces:**
- Consumes: Task 1 result key `Số phiếu đã xóa`.
- Produces: list update dialog displays the deletion count; form refresh routes to the list when the open document was deleted.

- [ ] **Step 1: Write failing Node behavior tests**

Load each actual client script in a VM with a minimal Frappe facade. Assert that the list result message includes `Số phiếu đã xóa: 2`, and that a form refresh response with one deletion calls `frappe.set_route("List", "VNT Attendance Confirm")` without calling `reload_doc`.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --test vinatex/vnt_hr/doctype/vnt_attendance_confirm/test_vnt_attendance_confirm_ui.js`

Expected: FAIL because neither client handles the deletion counter.

- [ ] **Step 3: Implement minimal client feedback**

Add the deletion line to the list result and branch the form callback to show a deletion alert and route back to the list.

- [ ] **Step 4: Run tests and syntax checks**

Run the Node test command, then `node --check` for both modified client scripts. Expected: PASS and exit 0.

- [ ] **Step 5: Commit**

Commit tests and client changes with message `fix: handle deleted attendance confirmation in UI`.

### Task 3: Add and run controlled cleanup for existing empty records

**Files:**
- Create: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/data_repair.py`
- Create: `vinatex/vnt_hr/doctype/vnt_attendance_confirm/test_data_repair.py`

**Interfaces:**
- Consumes: Frappe database query and document deletion APIs.
- Produces: `delete_empty_confirmations(dry_run=True) -> dict` with identified names/count and deleted count.

- [ ] **Step 1: Write failing cleanup tests**

Prove dry-run reports candidates without deletion and live mode deletes each returned candidate with permissions ignored while returning exact counts.

- [ ] **Step 2: Run tests and verify RED**

Run: `env PYTHONPATH=$WORKTREE:$BENCH/apps/frappe $BENCH/env/bin/python -m unittest vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_data_repair -v`

Expected: ERROR because `data_repair.py` does not exist.

- [ ] **Step 3: Implement dry-run-capable cleanup**

Select only `docstatus < 2` parent names whose child count is zero, sort them, and delete via `frappe.delete_doc` only when `dry_run` is false.

- [ ] **Step 4: Run tests and verify GREEN**

Run Task 3 tests and the full Python attendance-confirm test modules. Expected: all pass.

- [ ] **Step 5: Commit**

Commit with message `feat: add empty confirmation cleanup`.

- [ ] **Step 6: Back up, dry-run, delete, and verify production data**

Create a site backup; run the repair in dry-run and require the expected candidate list; run live deletion; query again and require zero empty non-cancelled parents. Record the backup path and counts in the execution ledger.

### Task 4: Whole-scope verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: fresh test, syntax, diff, and production-data evidence for final review.

- [ ] **Step 1: Run the Python modules and Node tests**

Expected: all tests pass.

- [ ] **Step 2: Run compile/syntax checks and inspect the branch diff**

Expected: Python compile and JavaScript syntax checks exit 0; only planned files changed after the prior branch commit.

- [ ] **Step 3: Commit any plan/spec tracking artifacts**

Commit with message `docs: record empty confirmation repair plan` if not already included.

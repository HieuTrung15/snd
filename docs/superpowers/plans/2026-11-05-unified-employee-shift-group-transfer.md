# Unified Employee Shift Group Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép HR chuyển kíp có ngày hiệu lực từ Employee Form hoặc Employee List bằng một workflow chung, đồng thời đồng bộ membership, ca kế hoạch, Attendance hoàn tất, phiếu giải trình và cache “Kíp hiện tại”.

**Architecture:** Một facade server chọn normal/backdated engine hoàn toàn theo ngày server, còn một module JavaScript dùng chung cung cấp dialog/preview/execute cho cả Form và List. `VNT Shift Group Assignment` là nguồn hiệu lực; `Employee.custom_shift_group` là cache theo ngày hiện tại, được đồng bộ sau transfer và bởi daily scheduler, còn direct save bị chặn.

**Tech Stack:** Python 3, Frappe/HRMS v15, MariaDB, JavaScript Desk UI, Python `unittest`, Node test runner.

**Spec:** `docs/superpowers/specs/2026-11-05-unified-employee-shift-group-transfer-design.md`

## Global Constraints

- `VNT Shift Group Assignment` là nguồn xác định kíp theo ngày; `Employee.custom_shift_group` chỉ là cache của ngày hiện tại.
- Employee Form và Employee List phải gọi cùng facade và cùng dialog; mode không được lấy từ input do browser quyết định.
- Backdate chỉ dành cho HR Manager/System Manager, cần preview token và chuỗi `XÁC NHẬN HỒI TỐ`.
- Batch all-or-nothing; một blocker hoặc stale preview không được ghi một phần.
- Không tạo/xóa Employee Checkin hoặc sửa `time`/`log_type`.
- Không tạo/chốt Attendance cho work date hôm nay hoặc tương lai.
- Current-day Checkin chỉ được giữ khi auto assignment hôm nay đã đúng target group/shift và không có action hôm nay; current-day Attendance vẫn block.
- Manual/legacy assignment, protected Attendance, kết quả HR và submitted Salary Slip vẫn là blocker.
- Chuyển tương lai không được hiển thị kíp đích như “Kíp hiện tại” trước ngày hiệu lực.
- Giữ mọi file trên branch `develop` local hiện tại; không commit và không push.

## Review Focus

- Form có thay đổi chưa lưu ngoài kíp: field kíp phải revert, dialog không mở và dữ liệu chưa lưu không bị mất.
- Effective date tương lai: membership/plan được tạo ngay nhưng cache giữ kíp nguồn, rồi daily scheduler đổi đúng ngày.
- Cache Employee lệch nhưng membership đã là target: preview báo mismatch, execution không tạo membership trùng và chỉ repair dữ liệu cần thiết.
- Checkin hôm nay: exact target auto assignment thì preserve; thiếu/mismatch/manual/OFF hoặc có Attendance hôm nay thì block.
- Batch nhiều Employee/stale token: một lỗi phải giữ nguyên toàn bộ batch, không sync cache hay refresh confirmation một phần.

---

### Task 1: Tạo facade server thống nhất cho Form và List

**Files:**
- Create: `vinatex/vnt_hr/shift_management/shift_group_transfer_workflow.py`
- Create: `vinatex/vnt_hr/shift_management/test_shift_group_transfer_workflow.py`

**Interfaces:**
- Consumes: `preview_bulk_shift_group_transfer(...)`, `execute_bulk_shift_group_transfer(...)`, `preview_backdated_shift_group_transfer(...)`, `execute_backdated_shift_group_transfer(...)`.
- Produces: `preview_shift_group_transfer(employees, target_shift_group, effective_date, membership_end_date, generate_until=None, note=None) -> dict`; `execute_shift_group_transfer(employees, target_shift_group, effective_date, membership_end_date, generate_until=None, note=None, preview_token=None, confirmation_text=None) -> dict`.

- [ ] **Step 1: Viết test đỏ cho định tuyến và hợp đồng response**

Thêm các test `test_preview_routes_past_date_to_backdated_service`, `test_preview_routes_today_and_future_to_normal_service`, `test_execute_does_not_trust_client_mode`, `test_backdated_execute_forwards_token_and_phrase`, và `test_facade_normalizes_common_result_keys`. Patch ngày server thành `2026-11-05`; assert `2026-11-01` đi backdated, `2026-11-05/06` đi normal, và mọi response có `mode`, `employees`, `target_shift_group`, `effective_date` phù hợp.

- [ ] **Step 2: Chạy test facade và xác nhận RED**

Run:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_shift_group_transfer_workflow -v`

Expected: FAIL vì module/facade chưa tồn tại.

- [ ] **Step 3: Implement facade và common result contract**

Facade tự gọi `getdate(today())`, không nhận `mode`. Với preview normal, bổ sung `mode="NORMAL"`; với execute của cả hai engine, bổ sung common keys mà không làm mất counts/operation id/job id hiện có. Giữ nguyên endpoint cũ để tương thích và không sao chép policy nghiệp vụ sang facade.

- [ ] **Step 4: Chạy test facade và service hiện có**

Run lệnh Step 2, rồi:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_service -v`

Expected: tất cả PASS; facade không nới quyền hoặc validation của delegate.

- [ ] **Step 5: Kiểm tra diff task**

Run: `/home/snd/frappe-bench/env/bin/python -m py_compile vinatex/vnt_hr/shift_management/shift_group_transfer_workflow.py vinatex/vnt_hr/shift_management/test_shift_group_transfer_workflow.py && git diff --check`

Expected: exit 0; giữ thay đổi uncommitted, không push.

### Task 2: Biến “Kíp hiện tại” thành cache theo membership có hiệu lực

**Files:**
- Create: `vinatex/vnt_hr/shift_management/current_shift_group_sync.py`
- Create: `vinatex/vnt_hr/shift_management/test_current_shift_group_sync.py`
- Create: `vinatex/vinatex/doctype/overrides/test_employee_shift_group_guard.py`
- Modify: `vinatex/vnt_hr/shift_management/shift_group_transfer_service.py`
- Modify: `vinatex/vnt_hr/shift_management/backdated_shift_group_transfer_service.py`
- Modify: `vinatex/vnt_hr/shift_management/backdated_shift_group_transfer_policy.py`
- Modify: `vinatex/vnt_hr/shift_management/test_backdated_shift_group_transfer_policy.py`
- Modify: `vinatex/vnt_hr/shift_management/scheduler.py`
- Modify: `vinatex/vinatex/doctype/overrides/employee.py`
- Modify: `vinatex/vnt_hr/doctype/vnt_shift_group/test_vnt_shift_group.py`

**Interfaces:**
- Consumes: Active `VNT Shift Group Assignment` rows and existing Employee display fields.
- Produces: `resolve_active_shift_group(employee: str, as_of_date=None) -> str | None`; `sync_employee_current_shift_groups(employee_names: list[str] | None = None, as_of_date=None) -> dict`; preview row keys `authoritative_shift_group`, `display_shift_group`, `display_mismatch`; `VntEmployee._validate_shift_group_change_uses_transfer_workflow() -> None`.

- [ ] **Step 1: Viết test đỏ cho resolver và cache sync**

Test exact-one active membership, no active membership, overlapping active memberships, today/backdated target, future transfer và cache/membership mismatch. Assert: exact-one trả group; no-active không xóa giá trị legacy và count `SKIPPED_NO_ACTIVE_MEMBERSHIP`; overlap raise `ValidationError`; transfer today/backdated cache thành target; future transfer giữ source trước ngày hiệu lực và đổi target khi gọi sync với đúng ngày hiệu lực; preview lấy authoritative group từ membership và đặt `display_mismatch=true` khi cache khác. Bổ sung regression `test_display_mismatch_target_membership_is_repaired_without_duplicate`, đồng thời siết `test_execute_rejects_stale_token_before_write` và `test_failure_rolls_back_all_employees` để assert cache/confirmation của toàn batch vẫn nguyên khi execute thất bại.

- [ ] **Step 2: Chạy sync tests và xác nhận RED**

Run:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_current_shift_group_sync -v`

Expected: FAIL vì helper chưa tồn tại.

- [ ] **Step 3: Implement resolver/sync và tích hợp hai engine**

Query membership theo batch, group theo Employee và require tối đa một dòng bao phủ `as_of_date`. Sau membership action/generation thành công, normal và backdated service gọi sync cho Employee trong request với ngày server; bỏ direct `frappe.db.set_value` trùng trong backdated service. Cả normal preview và backdated planner trả ba display/authoritative keys; action `ALREADY_TARGET` chỉ repair cache/lịch sử, không tạo membership mới. Result thêm counts sync nhưng vẫn nằm trong transaction hiện có.

- [ ] **Step 4: Viết test đỏ cho daily rollover**

Trong `test_current_shift_group_sync.py`, patch `scheduler.sync_employee_current_shift_groups` và `generate_shift_assignments`; assert `run_daily_shift_assignment_generation()` gọi sync trước generator, và lỗi sync không bị nuốt để tránh sinh ca trên cache lệch.

- [ ] **Step 5: Tích hợp daily scheduler và chạy sync/service tests**

Run Task 2 Step 2 và:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.doctype.vnt_shift_group.test_vnt_shift_group vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_policy vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_service -v`

Expected: PASS; test future transfer tiếp tục thấy source cache trước effective date, test today thấy target cache, và mismatch target-existing không tạo membership trùng.

- [ ] **Step 6: Viết test đỏ cho direct-save guard**

Thêm `test_existing_employee_cannot_save_changed_shift_group_directly`, `test_unchanged_shift_group_is_allowed`, và `test_new_employee_without_shift_group_is_allowed`. Test đầu assert message hướng HR dùng dialog có ngày hiệu lực; guard không dựa vào JavaScript.

- [ ] **Step 7: Implement server guard và chạy Employee tests**

Gọi `_validate_shift_group_change_uses_transfer_workflow()` từ `VntEmployee.validate()`. So sánh với `get_doc_before_save()` chỉ cho Employee hiện hữu; controlled DB write của sync không đi qua guard.

Run:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vinatex.doctype.overrides.test_employee_shift_group_guard vinatex.vinatex.doctype.overrides.test_employee_contract_history -v`

Expected: PASS.

- [ ] **Step 8: Kiểm tra task**

Run: `/home/snd/frappe-bench/env/bin/python -m py_compile vinatex/vnt_hr/shift_management/current_shift_group_sync.py vinatex/vnt_hr/shift_management/scheduler.py vinatex/vinatex/doctype/overrides/employee.py && git diff --check`

Expected: exit 0; không commit/push.

### Task 3: Giữ punch hôm nay khi target assignment đã đúng và không bị tác động

**Files:**
- Modify: `vinatex/vnt_hr/shift_management/backdated_shift_group_transfer_policy.py`
- Modify: `vinatex/vnt_hr/shift_management/test_backdated_shift_group_transfer_policy.py`
- Modify: `vinatex/vnt_hr/shift_management/test_backdated_shift_group_transfer_service.py`

**Interfaces:**
- Consumes: `assignments_by_date`, target plan và Checkin/Attendance snapshot hiện có.
- Produces: `_validate_current_day_checkins(checkins, attendance_by_name, assignments_by_date, target_plan, request, block) -> list[str]` trả names của current-day Checkin được preserve.

- [ ] **Step 1: Viết test đỏ cho ma trận current-day safety**

Thêm:

- `test_current_day_checkin_is_preserved_when_exact_target_auto_assignment_exists`;
- `test_current_day_checkin_blocks_when_target_assignment_is_missing`;
- `test_current_day_checkin_blocks_when_assignment_group_or_shift_differs`;
- `test_current_day_checkin_blocks_for_manual_assignment_or_target_off`;
- `test_current_day_attendance_still_blocks_even_when_assignment_matches`.

Case allow phải assert plan `READY`, không có `CURRENT_WORK_DATE_DATA`, punch có trong `preserved_checkins`, và không có assignment/attendance action ngày `2026-11-05`. Các case còn lại assert `BLOCKED`.

- [ ] **Step 2: Chạy policy tests và xác nhận RED**

Run:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_policy -v`

Expected: exact target current-day case FAIL vì policy hiện block mọi punch thuộc work date hôm nay.

- [ ] **Step 3: Implement preserve rule tối thiểu**

Truyền `assignments_by_date` vào validator. Chỉ return preserve khi có đúng một Active assignment hôm nay, đủ marker auto, group/shift trùng target, target không OFF và planner không có action hôm nay; mọi trường hợp không chứng minh được tiếp tục block. Không thay đổi vòng lặp block Attendance hôm nay.

- [ ] **Step 4: Chạy policy và backdated service tests**

Run Task 3 Step 2 và:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_service -v`

Expected: PASS; execution không cancel/rewrite current-day assignment, Attendance hoặc punch.

- [ ] **Step 5: Kiểm tra pure-policy diff**

Run: `/home/snd/frappe-bench/env/bin/python -m py_compile vinatex/vnt_hr/shift_management/backdated_shift_group_transfer_policy.py && git diff --check`

Expected: exit 0; không commit/push.

### Task 4: Tách dialog chuyển kíp dùng chung và chuyển Employee List sang facade

**Files:**
- Create: `vinatex/public/js/shift_group_transfer_dialog.js`
- Create: `vinatex/vnt_hr/shift_management/test_shift_group_transfer_dialog.js`
- Modify: `vinatex/vnt_hr/shift_management/employee_list.js`
- Modify: `vinatex/vnt_hr/shift_management/test_employee_list_backdated_transfer_ui.js`
- Modify: `vinatex/hooks.py`

**Interfaces:**
- Consumes: Task 1 facade endpoints và response contract.
- Produces: global/CommonJS `VNTShiftGroupTransferUI`; `openTransferDialog({frappe, employees, initialTargetShiftGroup=null, title=null, onCompleted=null}) -> Dialog`; pure helpers `isBackdated`, `buildPreviewCall`, `buildExecuteCall`, `canExecutePreview`, `renderPlanDetails`.

- [ ] **Step 1: Viết test đỏ cho shared dialog/facade call**

Test past/today/future đều gọi `shift_group_transfer_workflow.preview_shift_group_transfer`; execute gọi facade, backdate vẫn yêu cầu role/token/phrase; initial target được điền sẵn; blocked preview không có execute; `onCompleted` chỉ chạy cho `COMPLETED`/`ALREADY_APPLIED`, không chạy khi lỗi; `QUEUED` chỉ hoàn tất qua realtime event; copy tương lai nói “đã lên lịch”.

- [ ] **Step 2: Chạy Node tests và xác nhận RED**

Run:

`node --test vinatex/vnt_hr/shift_management/test_shift_group_transfer_dialog.js vinatex/vnt_hr/shift_management/test_employee_list_backdated_transfer_ui.js`

Expected: FAIL vì shared module/facade wiring chưa tồn tại.

- [ ] **Step 3: Di chuyển dialog/renderer sang public module**

Đưa toàn bộ field definition, period validation, warning, preview renderer, confirmation và result renderer khỏi `employee_list.js`. Add `/assets/vinatex/js/shift_group_transfer_dialog.js` vào `app_include_js` trước doctype scripts; module export cho Node và browser.

- [ ] **Step 4: Rút gọn Employee List adapter**

`employee_list.js` chỉ còn setup action, lấy checked names, gọi `VNTShiftGroupTransferUI.openTransferDialog(...)`, refresh list/realtime. Không giữ bản sao endpoint, date rule hoặc preview renderer.

- [ ] **Step 5: Chạy Node/syntax tests**

Run:

`node --test vinatex/vnt_hr/shift_management/test_shift_group_transfer_dialog.js vinatex/vnt_hr/shift_management/test_employee_list_backdated_transfer_ui.js && node --check vinatex/public/js/shift_group_transfer_dialog.js && node --check vinatex/vnt_hr/shift_management/employee_list.js`

Expected: PASS.

- [ ] **Step 6: Kiểm tra task**

Run: `git diff --check`

Expected: exit 0; không commit/push.

### Task 5: Tích hợp Employee Form với ngày hiệu lực và chống mất thay đổi chưa lưu

**Files:**
- Modify: `vinatex/vinatex/doctype/overrides/employee.js`
- Create: `vinatex/vinatex/doctype/overrides/test_employee_shift_group_ui.js`

**Interfaces:**
- Consumes: `VNTShiftGroupTransferUI.openTransferDialog(...)` từ Task 4 và server guard từ Task 2.
- Produces: `captureShiftGroupBaseline(frm) -> object`; `hasNonShiftGroupChanges(baseline, doc) -> boolean`; `handleShiftGroupChange(frm, frappe, transferUI) -> Promise<void>`.

- [ ] **Step 1: Viết Node test đỏ cho Employee Form**

Test các hành vi:

- saved Employee đổi `4 → 3`: field revert về `4`, dialog mở cho đúng một Employee, target `3` được điền sẵn và có ngày hiệu lực;
- cancel/blocked preview giữ `4` và không save;
- execution success reload doc;
- unrelated dirty field làm field revert, dialog không mở và hiện yêu cầu lưu trước;
- clear target, user không có role và double onchange đều không tạo request trái phép;
- Employee mới chọn kíp bị revert về giá trị cũ/null, không mở dialog và được yêu cầu lưu hồ sơ trước.

- [ ] **Step 2: Chạy form UI test và xác nhận RED**

Run:

`node --test vinatex/vinatex/doctype/overrides/test_employee_shift_group_ui.js`

Expected: FAIL vì Employee form chưa có workflow.

- [ ] **Step 3: Implement baseline, onchange adapter và reload**

Capture normalized saved-doc baseline ở `refresh`; loại các key UI/volatile nhưng không bỏ child data. Trong handler, lưu target, guarded-revert về baseline để không recurse, kiểm role/saved doc/non-shift dirtiness, rồi gọi shared dialog với `[frm.doc.name]`. `onCompleted` reload; nếu future effective date, message giải thích cache hiện tại chỉ đổi vào ngày hiệu lực.

- [ ] **Step 4: Chạy form/shared/list UI tests và syntax**

Run:

`node --test vinatex/vinatex/doctype/overrides/test_employee_shift_group_ui.js vinatex/vnt_hr/shift_management/test_shift_group_transfer_dialog.js vinatex/vnt_hr/shift_management/test_employee_list_backdated_transfer_ui.js && node --check vinatex/vinatex/doctype/overrides/employee.js`

Expected: PASS; không có hai dialog khi guarded `set_value` phát lại onchange.

- [ ] **Step 5: Kiểm tra task**

Run: `git diff --check`

Expected: exit 0; không commit/push.

### Task 6: Cập nhật tài liệu vận hành và chạy regression toàn phạm vi

**Files:**
- Modify: `docs/VNT_SHIFT_KIP_ATTENDANCE_IMPLEMENTATION.md`
- Modify: `docs/Huong_dan_quan_ly_ca_kip_va_cham_cong_HR.docx`
- Modify: `vinatex/translations/vi.csv`

**Interfaces:**
- Consumes: workflow hoàn chỉnh Tasks 1–5.
- Produces: hướng dẫn HR cho Form/List, normal/future/backdated, blockers và quy tắc dữ liệu hôm nay.

- [ ] **Step 1: Cập nhật source-of-truth documentation**

Ghi rõ membership là nguồn theo ngày, cache Employee, dialog trên Form, dialog List, ý nghĩa preview, future scheduling, backdated confirmation, current-day preserve và blocker. Trong DOCX, dùng quy trình chỉnh sửa hiện có để không phá style/heading/table; không mô tả direct Save field như một cách chuyển kíp.

- [ ] **Step 2: Cập nhật translation cho copy mới**

Thêm message facade/form/sync và result scheduled; không tạo duplicate key mâu thuẫn với copy hồi tố hiện có.

- [ ] **Step 3: Chạy named Python suites**

Run:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_shift_group_transfer_workflow vinatex.vnt_hr.shift_management.test_current_shift_group_sync vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_policy vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_service vinatex.vnt_hr.doctype.vnt_shift_group.test_vnt_shift_group vinatex.vnt_hr.shift_management.test_attendance_processing vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm vinatex.vnt_hr.shift_management.test_sunday_workday_policy vinatex.vinatex.doctype.overrides.test_employee_shift_group_guard vinatex.vinatex.doctype.overrides.test_employee_contract_history -v`

Expected: PASS.

- [ ] **Step 4: Chạy toàn bộ UI/syntax/diff checks**

Run Node commands Tasks 4–5, `py_compile` mọi Python file mới/sửa và `git diff --check`.

Expected: exit 0; `git log origin/develop..HEAD --oneline` rỗng; không commit/push.

- [ ] **Step 5: Review theo năm Review Focus**

Đối chiếu từng dòng Review Focus với test sở hữu; kiểm diff không thay source `frappe`, `erpnext`, `hrms`; mọi Critical/Important phải có test đỏ trước fix. Ghi lại bằng chứng lệnh chạy, không tạo commit.

### Task 7: Deploy local và xử lý Đinh Văn Sỹ qua workflow mới

**Files:**
- No new source; deploy và xác minh site `hrmsnd.vinatex.com.vn`.

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: runtime mới và dữ liệu `NMSVNĐ00092` nhất quán từ `01/11/2026` mà không chốt ngày `05/11`.

- [ ] **Step 1: Backup và chụp baseline trước migration**

Backup site. Snapshot field-by-field Employee, active/future memberships, Shift Assignments `01/11–31/12`, Checkins/Attendance `01/11–05/11`, và VNT Attendance Confirm tháng 11 của `NMSVNĐ00092`. Require baseline cache `4`, target membership/assignment `3`; nếu khác, dừng trước write và báo lại.

- [ ] **Step 2: Migrate/build/reload runtime local**

Chạy migrate nếu schema cần, build Vinatex assets, clear cache và reload web/workers/scheduler theo quy trình bench hiện hành. Require shared JS asset tải được và facade endpoint trả permission đúng.

- [ ] **Step 3: Preview request production**

Từ Employee Form chọn target `3`, effective `2026-11-01`, membership end/generate `2026-12-31`, note audit. Require preview `READY`, `completed_through=2026-11-04`, có `display_mismatch`, không tạo membership đích trùng, punch `05/11 05:56:31` nằm trong preserved checkins và không có action ngày `05/11`.

- [ ] **Step 4: Backup ngay trước write và execute bằng preview token**

Tạo backup thứ hai, nhập đúng `XÁC NHẬN HỒI TỐ`, execute nguyên request/token vừa preview. Expected `COMPLETED` hoặc `ALREADY_APPLIED`; không có partial error.

- [ ] **Step 5: Verify dữ liệu sau execution**

Require `Employee.custom_shift_group=3`; một membership kíp `3` hợp lệ, không duplicate; Attendance/confirmation `01/11–04/11` khớp target schedule và punches; không tạo/chốt Attendance work date `05/11`; raw Checkin count/time/log_type và punch `05:56:31` không đổi. Preview/execute lặp không tạo dữ liệu trùng.

- [ ] **Step 6: Xác minh branch/runtime cuối**

Require site hoạt động, scheduler enabled, named tests vẫn PASS, `HEAD == origin/develop`, `git log origin/develop..HEAD --oneline` rỗng. Toàn bộ source/docs tiếp tục là thay đổi local chưa commit; không push.

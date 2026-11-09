# Safe Backdated Shift Group Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép HR Manager/System Manager chuyển kíp hồi tố cho các Employee được chọn ngay trên dialog hiện tại, với preview, audit, tính lại Attendance an toàn và trường hợp đầu tiên là Trần Hữu Phúc từ 01/11/2026.

**Architecture:** Giữ nguyên service chuyển ngày hiện tại/tương lai; ngày quá khứ đi qua planner/service hồi tố riêng. Planner thuần tạo action plan và token từ snapshot, service revalidate dưới lock rồi thực hiện all-or-nothing; UI bắt buộc preview và câu xác nhận mạnh trước execute.

**Tech Stack:** Python 3, Frappe/HRMS v15, MariaDB, JavaScript Desk UI, `unittest`, Node test runner.

**Spec:** `docs/superpowers/specs/2026-11-05-safe-backdated-shift-group-transfer-design.md`

## Global Constraints

- Backdate chỉ dành cho HR Manager/System Manager; backend tự kiểm tra quyền.
- Tối đa 20 Employee và 366 ngày mỗi batch; một batch có một kíp đích.
- Không tạo/xóa Employee Checkin hoặc sửa `time`/`log_type`.
- Punch đã thuộc Attendance trước effective date không được dùng lại.
- Không tạo/chốt Attendance cho work date hôm nay hoặc tương lai.
- Manual/legacy assignment, leave/request, quyết định HR và submitted Salary Slip là blocker.
- Attendance legacy không có bằng chứng Checkin + auto assignment là blocker.
- Luồng hiện tại/tương lai và `_validate_request` tiếp tục từ chối backdate.
- Thực thi all-or-nothing, cần preview token còn hiệu lực và chuỗi `XÁC NHẬN HỒI TỐ`.
- Giữ mọi file trên `develop` local; không commit và không push.

## Review Focus

- Punch sau 00:00 đã liên kết Attendance trước effective date phải được giữ, dù nằm trên calendar date đầu kỳ hồi tố.
- Checkin hôm nay thuộc đuôi ca Đêm hôm trước được dùng; Checkin thuộc work date hôm nay phải block.
- Attendance legacy `Absent` không Checkin không được tự coi là pipeline output và cancel.
- Target schedule OFF trên ngày lịch sử phải bỏ auto assignment mà vẫn giữ audit; manual assignment cùng ngày phải block.
- Token phải đổi khi bất kỳ membership, schedule, assignment, Attendance, Checkin hoặc request field nào đổi sau preview.

---

### Task 1: Gắn provenance cho Attendance do pipeline tạo

**Files:**
- Modify: `vinatex/vnt_hr/custom/attendance.json`
- Modify: `vinatex/vnt_hr/attendance_processing.py`
- Modify: `vinatex/vnt_hr/shift_management/test_attendance_processing.py`

**Interfaces:**
- Consumes: `build_shift_windows(...)`, Shift Assignment engine marker.
- Produces: `Attendance.custom_vnt_generated_by_pipeline: Check`, `Attendance.custom_vnt_source_shift_assignment: Link`, và `window.shift_assignment`.

- [ ] **Step 1: Viết test đỏ provenance**

Thêm `test_window_exposes_source_shift_assignment` và `test_attendance_values_include_pipeline_provenance`. Assert source assignment name đi từ plan/window vào values khi tạo Attendance; không tự đánh dấu Attendance ngoài pipeline.

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_attendance_processing -v`

Expected: FAIL vì window/value chưa có provenance.

- [ ] **Step 3: Thêm schema và helper tạo Attendance values**

Thêm hai Custom Field read-only/hidden vào `attendance.json`. Trong `attendance_processing.py`, truyền `plan.shift_assignment` vào window và tách `_build_attendance_values(employee, window, details) -> dict`; helper chỉ set marker/link khi source assignment có thật.

- [ ] **Step 4: Chạy test và xác nhận GREEN**

Run lệnh Step 2.

Expected: PASS.

- [ ] **Step 5: Kiểm tra schema/code local**

Run: `/home/snd/frappe-bench/env/bin/python -m py_compile vinatex/vnt_hr/attendance_processing.py vinatex/vnt_hr/shift_management/test_attendance_processing.py && git diff --check`

Expected: exit 0; không commit/push.

### Task 2: Xây planner và preview hồi tố

**Files:**
- Create: `vinatex/vnt_hr/shift_management/backdated_shift_group_transfer_policy.py`
- Create: `vinatex/vnt_hr/shift_management/backdated_shift_group_transfer_service.py`
- Create: `vinatex/vnt_hr/shift_management/test_backdated_shift_group_transfer_policy.py`
- Create: `vinatex/vnt_hr/shift_management/test_backdated_shift_group_transfer_service.py`
- Modify: `vinatex/vnt_hr/shift_management/constants.py`

**Interfaces:**
- Consumes: Employee/membership/schedule/assignment/Checkin/Attendance/confirmation/Salary Slip snapshots.
- Produces: `build_backdated_employee_plan(snapshot: dict, request: dict) -> dict` với keys `employee`, `status`, `blockers`, `attendance_actions`, `assignment_actions`, `membership_action`, `preserved_checkins`; `make_preview_token(snapshot: dict, request: dict) -> str`; `preview_backdated_shift_group_transfer(...) -> dict` với keys `mode`, `preview_token`, `completed_through`, `counts`, `rows`.

- [ ] **Step 1: Viết test đỏ cho policy**

Thêm test cho: Employee bất kỳ; boundary punch được preserve; previous-night tail hôm nay được dùng; current-work-date log block; legacy Attendance có/không provenance; manual assignment; target OFF; confirmed explanation; Salary Slip; membership end trước hôm nay; batch >20. Mỗi test assert action/blocker đầu ra từ planner thật.

- [ ] **Step 2: Chạy policy test và xác nhận RED**

Run: `env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_policy -v`

Expected: FAIL vì module chưa tồn tại.

- [ ] **Step 3: Implement pure policy và token canonical**

Implement hai interface đã nêu. Token dùng SHA-256 của request đã normalize và snapshot canonical gồm name/modified/docstatus cùng giá trị nghiệp vụ; sort mọi collection trước serialize. Thêm `MAX_BACKDATED_TRANSFER_EMPLOYEES = 20` và `BACKDATED_TRANSFER_CONFIRMATION = "XÁC NHẬN HỒI TỐ"` trong constants.

- [ ] **Step 4: Chạy policy test và xác nhận GREEN**

Run lệnh Step 2.

Expected: PASS.

- [ ] **Step 5: Viết test đỏ cho preview service**

Thêm `test_preview_requires_manager_role`, `test_preview_returns_per_employee_actions_and_token`, `test_preview_is_read_only`, `test_preview_blocks_entire_batch_when_one_employee_is_unsafe`, và `test_normal_transfer_still_rejects_backdate`.

- [ ] **Step 6: Chạy service test và xác nhận RED**

Run: `env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_service -v`

Expected: FAIL vì preview endpoint/snapshot loader chưa hoàn chỉnh.

- [ ] **Step 7: Implement preview endpoint và snapshot loader**

Implement `preview_backdated_shift_group_transfer(employees, target_shift_group, effective_date, membership_end_date, generate_until=None, note=None) -> dict`. Dùng batched reads; không ghi/commit; trả `mode`, `preview_token`, `counts`, `rows`, `completed_through`, action summaries và blockers.

- [ ] **Step 8: Chạy hai test module và suite lân cận**

Run hai lệnh unittest Task 2, rồi:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_attendance_processing vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm -v`

Expected: tất cả PASS.

### Task 3: Thực thi hồi tố nguyên tử và idempotent

**Files:**
- Modify: `vinatex/vnt_hr/shift_management/backdated_shift_group_transfer_service.py`
- Modify: `vinatex/vnt_hr/shift_management/test_backdated_shift_group_transfer_service.py`
- Modify: `vinatex/vnt_hr/attendance_processing.py`

**Interfaces:**
- Consumes: Task 2 preview/token/action plan, `process_attendance`, `generate_shift_assignments`, `make_attendance_confirm`.
- Produces: `execute_backdated_shift_group_transfer(..., preview_token, confirmation_text) -> dict` trả `status`, `operation_id`, `employees`, `counts`; `_rewrite_historical_auto_assignment(assignment, action, operation_id) -> None`; `_cancel_historical_auto_assignment(assignment, action, operation_id) -> None`.

- [ ] **Step 1: Viết test đỏ execute safety**

Thêm `test_execute_requires_exact_confirmation`, `test_execute_rejects_stale_token_before_write`, `test_execute_locks_and_rechecks_batch`, `test_failure_rolls_back_all_employees`, và `test_second_execute_returns_already_applied`.

- [ ] **Step 2: Chạy service test và xác nhận RED**

Run service test command Task 2 Step 6.

Expected: FAIL do execute chưa tồn tại.

- [ ] **Step 3: Implement transaction shell và audit id**

Implement public execute signature giống preview cộng `preview_token` và `confirmation_text`. Kiểm role/phrase, lock Employee theo name, reload snapshot, compare token, tạo operation UUID và chỉ bắt đầu ghi sau mọi guard. Không commit từng Employee.

- [ ] **Step 4: Viết test đỏ reconciliation**

Thêm test thực hành trên state fixture cho: cancel/recreate Attendance; preserve boundary link; rewrite auto assignment ngày làm; cancel auto assignment ngày OFF; manual blocker; membership close/create; Employee display fields; multi-month confirmation refresh; overnight tail; không tạo Attendance hôm nay.

- [ ] **Step 5: Chạy service test và xác nhận RED**

Run service test command.

Expected: transaction shell có nhưng state cuối chưa khớp.

- [ ] **Step 6: Implement reconciliation theo action plan**

Cancel Attendance bằng Document API; chỉ rewrite/cancel Shift Assignment có đủ engine marker và ghi Comment before snapshot; close/create membership; cập nhật display fields; generate ca; process completed work dates; refresh confirmation theo từng tháng. Helper cancel lịch sử phải assert mọi Attendance cùng Employee/ngày đã `docstatus=2`, không còn Checkin link, rồi mới DB-update đúng assignment sang `docstatus=2`, `status=Inactive`, `modified/modified_by`; assignment chưa dùng vẫn gọi Document `cancel()` chuẩn.

- [ ] **Step 7: Chạy service/policy/neighbor suites**

Run:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_policy vinatex.vnt_hr.shift_management.test_backdated_shift_group_transfer_service vinatex.vnt_hr.shift_management.test_attendance_processing vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm vinatex.vnt_hr.shift_management.test_sunday_workday_policy -v`

Expected: tất cả PASS.

### Task 4: Tích hợp dialog và tài liệu vận hành

**Files:**
- Modify: `vinatex/vnt_hr/shift_management/employee_list.js`
- Create: `vinatex/vnt_hr/shift_management/test_employee_list_backdated_transfer_ui.js`
- Modify: `vinatex/translations/vi.csv`
- Modify: `docs/VNT_SHIFT_KIP_ATTENDANCE_IMPLEMENTATION.md`

**Interfaces:**
- Consumes: preview/execute endpoint Tasks 2–3.
- Produces: UI chọn endpoint theo ngày, preview hồi tố, confirmation phrase.

- [ ] **Step 1: Viết Node test đỏ**

Test: future/today vẫn gọi service cũ; past date hiện warning và gọi preview mới; HR User không được hồi tố; blocked preview không có nút execute; READY yêu cầu đúng phrase; execute gửi nguyên request + token.

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `node --test vinatex/vnt_hr/shift_management/test_employee_list_backdated_transfer_ui.js`

Expected: FAIL vì UI chưa có nhánh hồi tố.

- [ ] **Step 3: Implement UI nhánh hồi tố**

Tách các helper thuần `isBackdated`, `buildPreviewCall`, `buildExecuteCall` để test. Giữ nguyên giao diện normal; bổ sung warning, action counts, boundary-punch info và dialog nhập phrase chỉ cho mode backdated.

- [ ] **Step 4: Cập nhật copy và source-of-truth doc**

Thêm translation cho toàn bộ thông báo backend/UI mới. Sửa BƯỚC 14/23 để mô tả ngoại lệ hồi tố có kiểm soát, role, preview token, blockers và audit; không xóa mô tả luồng thường.

- [ ] **Step 5: Chạy JS/Python suites và syntax checks**

Run Node test, `node --check vinatex/vnt_hr/shift_management/employee_list.js`, suite Python Task 3 Step 7, và `git diff --check`.

Expected: tất cả PASS; không commit/push.

### Task 5: Triển khai local production và hồi tố Trần Hữu Phúc

**Files:**
- No new source; deploy/migrate/reload local site `hrmsnd.vinatex.com.vn`.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: schema/runtime mới và dữ liệu Trần Hữu Phúc đã sửa.

- [ ] **Step 1: Backup trước migration và chụp baseline**

Tạo site backup. Lưu field-by-field snapshot/fingerprint cho Employee, membership, Shift Assignment 31/10–31/12, Checkin 31/10–05/11, Attendance 31/10–05/11 và confirmation tháng 11 của `NMSVNĐ00073`.

- [ ] **Step 2: Migrate, build và reload**

Chạy `bench --site hrmsnd.vinatex.com.vn migrate`, build assets Vinatex, clear cache và reload gunicorn/scheduler/workers. Require hai Attendance custom fields tồn tại và `/app` phản hồi bình thường.

- [ ] **Step 3: Preview production request**

Gọi preview mới với Employee `NMSVNĐ00073`, target `1`, effective `2026-11-01`, end/generate `2026-12-31`, note audit. Require `READY`; punch 05:59 được preserve; 01–04/11 action plan khớp spec; lưu token.

- [ ] **Step 4: Backup ngay trước write và execute bằng token**

Tạo backup thứ hai, rồi gọi execute với nguyên request, token vừa nhận và `XÁC NHẬN HỒI TỐ`. Expected: `COMPLETED`, operation id có giá trị, không blocker/error.

- [ ] **Step 5: Verify production và idempotency**

Require: Attendance/punch 31/10 không đổi; membership `6` kết thúc 31/10 và `1` bắt đầu 01/11; 53 target assignments; Attendance 01–04/11 đúng spec; no Attendance work date 05/11; confirmation còn 01/11 `MISSING_IN` và 02/11 `EARLY_EXIT` theo dung sai 3 phút hiện hành; raw Checkin count/time/type không đổi. Preview lại cùng request trả trạng thái đích và execute lặp trả `ALREADY_APPLIED`.

### Task 6: Xác minh toàn phạm vi và review fresh-context

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: test/compile/diff/production/review evidence.

- [ ] **Step 1: Chạy toàn bộ named suites và compile**

Chạy Python suite Task 3 Step 7, Node suite Task 4, `py_compile` mọi Python file mới/sửa và `node --check` UI.

- [ ] **Step 2: Kiểm tra git/runtime/production**

Chạy staged/unstaged `git diff --check`; require `HEAD == origin/develop`, zero outgoing commits, runtime đã reload; chạy lại production assertions Task 5.

- [ ] **Step 3: Review độc lập toàn scope**

Fresh reviewer đọc spec, plan, local diff, năm Review Focus và production evidence. Critical/Important vào một fix pass TDD; Minor ghi ledger. Giữ source/workspace trên `develop` local, không commit/push.


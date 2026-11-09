# Trần Hữu Phúc Backdated Shift Transfer Implementation Plan

> **Đã được thay thế:** Kế hoạch repair một nhân sự này được mở rộng thành `2026-11-05-safe-backdated-shift-group-transfer.md`. Không thực thi kế hoạch này.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hồi tố Trần Hữu Phúc từ kíp `6` sang kíp `1` kể từ 01/11/2026 mà không thay đổi Attendance 31/10 hoặc dùng trùng punch 05:59.

**Architecture:** Tạo một repair module khóa cứng đúng Employee/kíp/kỳ dữ liệu, với `preview`, dry-run mặc định, guard chống drift, thực thi nguyên tử và `verify`. Repair giữ audit bằng cách cancel Attendance cũ, sửa có kiểm soát ba Shift Assignment lịch sử, dùng pipeline attendance hiện hữu để tái tạo 01–04/11 và giữ nguyên lệnh cấm backdate của công cụ hàng loạt.

**Tech Stack:** Python 3, Frappe/HRMS Documents, MariaDB, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-05-tran-huu-phuc-backdated-shift-transfer-design.md`

## Global Constraints

- Employee duy nhất: `NMSVNĐ00073` — Trần Hữu Phúc.
- Kíp nguồn `6`; kíp đích `1`; hiệu lực `2026-11-01..2026-12-31`.
- Attendance `HR-ATT-2026-05291` ngày 31/10 và punch `EMP-CKIN-11-2026-000070` lúc 05:59 phải giữ nguyên từng trường và liên kết.
- Không tạo Attendance cho ngày công 05/11 hoặc muộn hơn.
- Không tạo, xóa hoặc sửa thời gian thô Employee Checkin.
- Không nới `_validate_request`; bulk transfer chung tiếp tục từ chối ngày quá khứ.
- Mọi ghi dữ liệu phải sau backup, guard nguồn và dry-run đạt yêu cầu.
- Giữ thay đổi trên `develop` local; không commit và không push.

## Review Focus

- Nếu punch 05:59 vẫn liên kết Attendance 31/10, repair không được lấy nó cho Attendance 01/11.
- Nếu có Checkin/Attendance hoặc quyết định HR mới sau preview, execute phải dừng trước lần ghi đầu tiên.
- Shift Đêm ngày 04/11 phải nhận punch 05:52 ngày 05/11 nhưng không tạo Attendance ngày công 05/11.
- Các thứ Sáu trong 01/11–31/12 phải OFF và không có Shift Assignment sau khi chuyển sang kíp `1`.
- Chạy execute lần hai phải là no-op `ALREADY_APPLIED`, không tạo membership, Attendance hoặc assignment trùng.

---

### Task 1: Xây repair hồi tố khóa đúng dữ liệu

**Files:**
- Create: `vinatex/vnt_hr/shift_management/tran_huu_phuc_backdated_shift_transfer.py`
- Create: `vinatex/vnt_hr/shift_management/test_tran_huu_phuc_backdated_shift_transfer.py`
- Verify: `vinatex/vnt_hr/shift_management/shift_group_transfer_service.py`

**Interfaces:**
- Consumes: `process_attendance(from_date, to_date, dry_run=False, employee_names=None)`, `make_attendance_confirm(...)`, `generate_shift_assignments(...)`, Frappe Document cancel/insert APIs.
- Produces: `preview() -> dict`, `execute(dry_run: bool = True) -> dict`, `verify() -> dict`.

- [ ] **Step 1: Viết test đỏ cho preview và guard**

Thêm `test_preview_returns_exact_repair_plan`, `test_source_drift_aborts_before_writes`, và `test_general_bulk_transfer_still_rejects_backdate`. Assert đúng Employee, membership, ba Attendance cần cancel, ba assignment lịch sử cần sửa, 49 assignment tương lai cần cancel, và bulk API vẫn báo lỗi backdate.

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_tran_huu_phuc_backdated_shift_transfer -v`

Expected: FAIL vì repair module chưa tồn tại.

- [ ] **Step 3: Tạo snapshot và pure repair plan**

Trong module mới, khóa hằng số Employee/kíp/ngày/docname đã duyệt. Implement `_load_snapshot() -> dict`, `_validate_snapshot(snapshot) -> None`, `_build_repair_plan(snapshot) -> dict`, và `preview() -> dict`. Guard gồm cấu hình kíp, membership, Attendance/Checkin biên tháng, confirmation chưa có quyết định HR, không có dữ liệu ngày công 05/11, và đúng tập auto assignment nguồn.

- [ ] **Step 4: Chạy test preview/guard và xác nhận GREEN**

Run lệnh Step 2.

Expected: các test preview/guard PASS; test execute tiếp theo chưa được thêm.

- [ ] **Step 5: Viết test đỏ cho execute và idempotency**

Thêm `test_execute_preserves_october_boundary`, `test_execute_rebuilds_completed_november_attendance`, `test_november_four_overnight_owns_next_day_punch`, `test_future_assignments_follow_group_one_matrix`, và `test_second_execute_is_already_applied`. Assert các giá trị bắt buộc trong spec, không assert vào mock call thay cho trạng thái đầu ra.

- [ ] **Step 6: Chạy test và xác nhận RED**

Run lệnh Step 2.

Expected: FAIL vì `execute`/`verify` chưa thực hiện mutation.

- [ ] **Step 7: Implement execute nguyên tử và verify độc lập**

Implement `execute(dry_run=True) -> dict` với dry-run mặc định. Khi ghi: revalidate snapshot; cancel ba Attendance 02–04/11; sửa ba assignment lịch sử theo ma trận kíp `1` và thêm audit comment; đóng/tạo membership; chạy attendance 01–04/11; cancel auto assignment kíp `6` chưa dùng từ 05/11; generate kíp `1` đến 31/12; refresh confirmation 01–04/11. Implement `verify() -> dict` bằng truy vấn độc lập và trả `PASS`/`FAIL` cùng mismatch list; trạng thái đích hoàn chỉnh trả `ALREADY_APPLIED` ở execute.

- [ ] **Step 8: Chạy test repair và suite lân cận**

Run lệnh Step 2, sau đó chạy:

`env PYTHONPATH=/home/snd/frappe-bench/apps/vinatex:/home/snd/frappe-bench/apps/frappe:/home/snd/frappe-bench/apps/erpnext:/home/snd/frappe-bench/apps/hrms /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_attendance_processing vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm vinatex.vnt_hr.shift_management.test_sunday_workday_policy -v`

Expected: tất cả PASS.

- [ ] **Step 9: Giữ thay đổi local**

Run: `/home/snd/frappe-bench/env/bin/python -m py_compile vinatex/vnt_hr/shift_management/tran_huu_phuc_backdated_shift_transfer.py vinatex/vnt_hr/shift_management/test_tran_huu_phuc_backdated_shift_transfer.py`, sau đó `git diff --check`. Không commit hoặc push.

### Task 2: Dry-run, backup và thực thi production

**Files:**
- No source changes; vận hành module Task 1 trên site `hrmsnd.vinatex.com.vn`.

**Interfaces:**
- Consumes: `preview()`, `execute(dry_run=True|False)` từ Task 1.
- Produces: membership/assignment/Attendance/confirmation đã sửa và backup có thể phục hồi.

- [ ] **Step 1: Chạy preview và dry-run**

Run `bench --site hrmsnd.vinatex.com.vn execute vinatex.vnt_hr.shift_management.tran_huu_phuc_backdated_shift_transfer.preview` và `execute --kwargs '{"dry_run": true}'`.

Expected: `READY`; đúng 3 Attendance cancel, 3 historical assignments sửa, 49 future assignments cancel, 53 ngày làm việc đích; không có blocker.

- [ ] **Step 2: Tạo backup và fingerprint nguồn**

Chạy site backup. Lưu fingerprint từng trường cho Employee Checkin 31/10–05/11, Attendance 31/10–04/11, memberships và Shift Assignments 01/11–31/12. Ghi riêng toàn bộ row của `HR-ATT-2026-05291` và `EMP-CKIN-11-2026-000070`.

- [ ] **Step 3: Thực thi một lần**

Run: `bench --site hrmsnd.vinatex.com.vn execute vinatex.vnt_hr.shift_management.tran_huu_phuc_backdated_shift_transfer.execute --kwargs '{"dry_run": false}'`

Expected: `COMPLETED`; mọi counter khớp preview; không lỗi và không mutation ngoài Employee đã khóa.

- [ ] **Step 4: Chạy verify và idempotency check**

Run `verify`, rồi chạy lại `execute --kwargs '{"dry_run": false}'`.

Expected: `verify.status = PASS`; lần hai trả `ALREADY_APPLIED` với zero writes.

### Task 3: Xác minh toàn phạm vi và review

**Files:**
- Verify only.

**Interfaces:**
- Consumes: code/test Task 1 và dữ liệu Task 2.
- Produces: bằng chứng test, production query, git state và review độc lập.

- [ ] **Step 1: Xác minh biên tháng và dữ liệu thô**

So sánh fingerprint: Attendance 31/10 và punch 05:59 giống hệt backup; số lượng/timestamp Checkin không đổi. Xác nhận ba Attendance cũ 02–04/11 là Cancelled và bốn Attendance mới 01–04/11 đúng shift/status/time; không có Attendance ngày 05/11.

- [ ] **Step 2: Xác minh lịch và giải trình**

Require đúng hai membership không chồng lấn; 53 assignment kíp `1` khớp ma trận, không còn assignment kíp `6` chưa cancel từ 01/11; confirmation 01–04/11 chỉ còn `01/11 MISSING_IN`.

- [ ] **Step 3: Chạy toàn bộ test/compile/diff checks**

Chạy hai lệnh unittest và lệnh `py_compile` của Task 1, staged/unstaged `git diff --check`; require `HEAD == origin/develop` và không có outgoing commit.

- [ ] **Step 4: Review fresh-context**

Review diff local, spec, plan, production evidence và năm Review Focus. Critical/Important được sửa trong một lượt TDD; Minor được ghi nhận. Giữ workspace và source trên `develop` local, không commit/push.


# Sync HC Holiday List on Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đồng bộ `Employee.holiday_list` từ master nhóm `HC` trong cùng giao dịch khi HR chuyển Employee từ kíp sang Hành chính.

**Architecture:** Mở rộng `current_shift_group_sync.py`, là điểm chung mà cả chuyển thường và hồi tố gọi sau khi thay membership, để cập nhật thêm Holiday List chỉ khi nhóm đang hiệu lực là `HC`. Facade workflow kiểm tra cấu hình Holiday List của HC trước cả preview và execute, nhờ đó HR thấy lỗi trước khi dữ liệu bị thay đổi.

**Tech Stack:** Frappe/ERPNext, Python, `unittest`, `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-11-05-sync-hc-holiday-list-on-transfer-design.md`

## Global Constraints

- Chỉ đồng bộ Holiday List khi nhóm đích là `HC`; không thay đổi Holiday List khi chuyển sang nhóm khác.
- Giá trị phải lấy từ `VNT Shift Group HC.holiday_list`, không mã hóa cứng `2026`.
- HC thiếu Holiday List phải làm preview/execute thất bại trước khi có thay đổi dữ liệu.
- Cùng quy tắc phải áp dụng cho Employee Form, Employee List, chuyển thường và hồi tố.
- Giữ toàn bộ thay đổi trên branch `develop` local; không commit và không push.
- Không thực hiện chuyển kíp cho Trần Thị Đỉnh trong lần triển khai này; chỉ kiểm tra bằng preview đọc-only.

## Review Focus

- Employee đã có `custom_shift_group = HC` nhưng còn Holiday List cũ vẫn phải được sửa; Task 1 có kiểm thử riêng.
- HC không có Holiday List không được tạo trạng thái cập nhật một phần; Task 1 xác nhận không gọi `set_value`, Task 2 xác nhận preview/execute bị chặn.
- Chuyển sang nhóm không phải HC phải giữ nguyên Employee Holiday List; Task 1 có kiểm thử hồi quy.
- Employee không có membership đang hiệu lực vẫn phải giữ cache và Holiday List cũ; chạy lại kiểm thử hiện có trong Task 1.
- Preview thường và hồi tố đều phải dùng cùng validation trước khi route; Task 2 kiểm thử cả hai ngày hiệu lực.

---

### Task 1: Đồng bộ Holiday List trong cache Employee

**Files:**
- Modify: `vinatex/vnt_hr/shift_management/current_shift_group_sync.py:22-97`
- Modify: `vinatex/vnt_hr/shift_management/test_current_shift_group_sync.py:10-250`

**Interfaces:**
- Produces: `get_required_hc_holiday_list(target_shift_group: str) -> str | None`; trả `None` cho nhóm khác HC, trả Holiday List của HC, hoặc ném `frappe.ValidationError` nếu HC thiếu cấu hình.
- Produces: `sync_employee_current_shift_groups(employee_names=None, as_of_date=None) -> dict`; giữ contract hiện có, nhưng cập nhật thêm `holiday_list` cho membership HC.

- [ ] **Step 1: Viết kiểm thử thất bại cho Employee HC có Holiday List cũ**

Mở rộng `_Store` để mô phỏng `VNT Shift Group.holiday_list`. Thêm `test_sync_hc_replaces_stale_employee_holiday_list_from_group_master`, với Employee `holiday_list = KIP-01-2026`, membership `HC`, master HC `holiday_list = 2026`; khẳng định kết quả `UPDATED` và Employee nhận `2026`.

- [ ] **Step 2: Viết kiểm thử thất bại cho trường hợp cache nhóm/type đã đúng nhưng Holiday List còn sai**

Thêm `test_sync_hc_does_not_report_unchanged_when_only_holiday_list_is_stale`; khẳng định vẫn trả `UPDATED` và sửa Holiday List.

- [ ] **Step 3: Viết kiểm thử thất bại cho HC thiếu Holiday List và nhóm không phải HC**

Thêm hai kiểm thử: `test_sync_hc_without_holiday_list_raises_before_employee_update` khẳng định `ValidationError` và không đổi Employee; `test_sync_non_hc_preserves_employee_holiday_list` khẳng định nhóm `3` vẫn giữ Holiday List cũ.

- [ ] **Step 4: Chạy kiểm thử mới để xác nhận RED**

Run: `python -m unittest vinatex.vnt_hr.shift_management.test_current_shift_group_sync.TestCurrentShiftGroupSync.test_sync_hc_replaces_stale_employee_holiday_list_from_group_master vinatex.vnt_hr.shift_management.test_current_shift_group_sync.TestCurrentShiftGroupSync.test_sync_hc_does_not_report_unchanged_when_only_holiday_list_is_stale vinatex.vnt_hr.shift_management.test_current_shift_group_sync.TestCurrentShiftGroupSync.test_sync_hc_without_holiday_list_raises_before_employee_update vinatex.vnt_hr.shift_management.test_current_shift_group_sync.TestCurrentShiftGroupSync.test_sync_non_hc_preserves_employee_holiday_list -v`

Expected: FAIL vì sync chưa đọc/cập nhật `holiday_list` và chưa validation HC.

- [ ] **Step 5: Cài đặt helper và mở rộng sync tối thiểu**

Thêm `get_required_hc_holiday_list(target_shift_group: str) -> str | None`. Trong `sync_employee_current_shift_groups`, đọc `Employee.holiday_list`, resolve Holiday List của HC một lần sau khi khóa/reload, đưa trường này vào điều kiện `UNCHANGED`, và chỉ thêm `holiday_list` vào payload `set_value` khi membership đích là `HC`.

- [ ] **Step 6: Chạy kiểm thử Task 1 để xác nhận GREEN và hồi quy**

Run: `python -m unittest vinatex.vnt_hr.shift_management.test_current_shift_group_sync -v`

Expected: toàn bộ module PASS.

### Task 2: Chặn preview và execute khi HC thiếu Holiday List

**Files:**
- Modify: `vinatex/vnt_hr/shift_management/shift_group_transfer_workflow.py:1-75`
- Modify: `vinatex/vnt_hr/shift_management/test_shift_group_transfer_workflow.py:1-120`

**Interfaces:**
- Consumes: `get_required_hc_holiday_list(target_shift_group: str) -> str | None` từ Task 1.
- Preserves: chữ ký và contract kết quả của `preview_shift_group_transfer(...) -> dict` và `execute_shift_group_transfer(...) -> dict`.

- [ ] **Step 1: Viết kiểm thử thất bại cho preview HC ở cả chế độ thường và hồi tố**

Thêm `test_preview_validates_hc_holiday_list_before_routing` với ngày `2026-11-05` và `2026-11-01`; mock helper ném `ValidationError`, khẳng định cả normal/backdated service đều không được gọi.

- [ ] **Step 2: Viết kiểm thử thất bại cho execute HC**

Thêm `test_execute_validates_hc_holiday_list_before_routing`; khẳng định execute service không được gọi khi helper báo HC thiếu cấu hình.

- [ ] **Step 3: Chạy kiểm thử mới để xác nhận RED**

Run: `python -m unittest vinatex.vnt_hr.shift_management.test_shift_group_transfer_workflow.TestShiftGroupTransferWorkflow.test_preview_validates_hc_holiday_list_before_routing vinatex.vnt_hr.shift_management.test_shift_group_transfer_workflow.TestShiftGroupTransferWorkflow.test_execute_validates_hc_holiday_list_before_routing -v`

Expected: FAIL vì facade chưa gọi validation.

- [ ] **Step 4: Gọi validation chung trước khi route**

Import helper Task 1 và gọi `get_required_hc_holiday_list(target_shift_group)` ngay đầu hai entry point preview/execute, trước `_mode_for` và trước khi gọi service con.

- [ ] **Step 5: Chạy kiểm thử Task 2 để xác nhận GREEN và hồi quy**

Run: `python -m unittest vinatex.vnt_hr.shift_management.test_shift_group_transfer_workflow -v`

Expected: toàn bộ module PASS.

### Task 3: Xác minh toàn bộ và kiểm tra production chỉ đọc

**Files:**
- Verify: `vinatex/vnt_hr/shift_management/current_shift_group_sync.py`
- Verify: `vinatex/vnt_hr/shift_management/shift_group_transfer_workflow.py`
- Verify: các test Python/Node của workflow chuyển kíp hiện có

**Interfaces:**
- Consumes: các contract đã hoàn thành ở Task 1 và Task 2.
- Produces: bằng chứng kiểm thử, reload runtime và preview đọc-only cho `NMSVNĐ00105`.

- [ ] **Step 1: Chạy toàn bộ test Python liên quan chuyển kíp và chấm công**

Run: `python -m unittest discover -s vinatex/vnt_hr/shift_management -p 'test_*.py' -v`

Expected: tất cả PASS, 0 failure/error.

- [ ] **Step 2: Chạy test UI chuyển kíp**

Run: `node --test vinatex/vnt_hr/shift_management/test_shift_group_transfer_dialog.js vinatex/vnt_hr/shift_management/test_employee_list_backdated_transfer_ui.js vinatex/vinatex/doctype/overrides/test_employee_shift_group_ui.js`

Expected: tất cả PASS.

- [ ] **Step 3: Chạy kiểm tra tĩnh**

Run: `python -m py_compile vinatex/vnt_hr/shift_management/current_shift_group_sync.py vinatex/vnt_hr/shift_management/shift_group_transfer_workflow.py && git diff --check`

Expected: exit code 0, không có output lỗi.

- [ ] **Step 4: Reload runtime an toàn**

Reload các process web/worker/scheduler đang chạy để Python mới được nạp; xác nhận site `hrmsnd.vinatex.com.vn` trả HTTP 200. Không migrate vì không có thay đổi schema.

- [ ] **Step 5: Chạy preview đọc-only cho Trần Thị Đỉnh**

Gọi `preview_shift_group_transfer` với Employee `NMSVNĐ00105`, nhóm `HC`, hiệu lực `2026-11-05`, kết thúc/tạo ca đến `2026-12-31`. Khẳng định `READY`, không blocker, master HC trả Holiday List `2026`, và dữ liệu Employee vẫn là Kíp 1/`KIP-01-2026` vì chưa execute.

- [ ] **Step 6: Kiểm tra trạng thái Git**

Run: `git status --short --branch && git log --oneline origin/develop..HEAD`

Expected: branch `develop`, thay đổi chỉ ở local, không có commit mới và không push.

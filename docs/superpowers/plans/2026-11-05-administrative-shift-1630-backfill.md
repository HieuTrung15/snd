# Administrative Shift 16:30 Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cập nhật nhất quán dữ liệu chấm công của ca Hành chính theo giờ 07:30–16:30 từ 01/10/2026 mà không làm thay đổi bằng chứng quẹt thẻ hoặc kết quả Attendance.

**Architecture:** Thêm một data-repair idempotent, có dry-run và guard cấu hình, để sửa metadata ca trên Employee Checkin kể cả khi đã liên kết Attendance. Sau backup và đối soát baseline, chạy repair rồi dùng API VNT Attendance Confirm sẵn có theo từng tháng; Attendance được kiểm tra checksum nhưng không ghi lại vì dry-run hiện tại chứng minh không có thay đổi nghiệp vụ.

**Tech Stack:** Python, Frappe/HRMS v15, MariaDB, `unittest`, Bench CLI.

**Spec:** `docs/superpowers/specs/2026-11-05-administrative-shift-1630-backfill-design.md`

## Global Constraints

- Ngày hiệu lực cố định là `2026-10-01`; không sửa dữ liệu trước ngày này.
- Shift Type mục tiêu là `Hành chính`, giờ danh nghĩa 07:30–16:30, buffer trước/sau đều 60 phút, nên cửa sổ thực tế là 06:30–17:30.
- Chỉ sửa `shift_start`, `shift_end`, `shift_actual_start`, `shift_actual_end` và `offshift` của Employee Checkin chưa hủy thuộc ca Hành chính.
- Không sửa `time`, `log_type`, `employee`, `attendance`, `skip_auto_attendance` hoặc `modified` của Employee Checkin.
- Không tạo, hủy hoặc sửa Attendance; checksum Attendance trước/sau phải giống nhau.
- Dòng VNT Attendance Confirm đã `confirm=1` phải được giữ làm dấu vết; chỉ dòng chưa xác nhận và không còn bất thường mới được xóa bởi API hiện hữu.
- Phải có database backup, dry-run và baseline ngay trước khi ghi.
- Không commit trong plan này: worktree đang chứa nhiều thay đổi chưa commit của người dùng; chỉ thêm đúng các file trong phạm vi sau khi được duyệt.

## Review Focus

- Checkin đã liên kết Attendance vẫn phải được sửa metadata ca nhưng liên kết `attendance` phải giữ nguyên (test ở Task 1, Step 1).
- Checkin trước `2026-10-01` hoặc đã hủy không được chọn (test ở Task 1, Step 1).
- Repair phải dừng mà không ghi nếu giờ/buffer của Shift Type khác 07:30–16:30/60/60 (test ở Task 1, Step 1).
- Checkin có `shift_start` thiếu phải dùng ngày của `time`; Checkin có `shift_start` phải dùng ngày ca đó, không suy diễn từ giờ OUT (test ở Task 1, Step 1).
- Chạy lại sau khi dữ liệu đã đúng phải báo `rows_to_update=0` và không gọi `set_value` (test ở Task 1, Step 1).

---

### Task 1: Data repair idempotent cho metadata ca trên Employee Checkin

**Files:**
- Modify: `vinatex/vnt_hr/shift_management/data_repair.py`
- Create: `vinatex/vnt_hr/shift_management/test_data_repair.py`

**Interfaces:**
- Consumes: DocType `Shift Type` và `Employee Checkin`; `frappe.utils.getdate`, `get_time`; cấu hình hiện hành của `Hành chính`.
- Produces: `repair_administrative_shift_checkins(effective_from="2026-10-01", dry_run=True) -> dict` với các khóa `effective_from`, `dry_run`, `matched_rows`, `linked_rows`, `rows_to_update`, `updated_rows`, `already_correct`.

- [ ] **Step 1: Viết các test thất bại cho phạm vi, guard và tính idempotent**

Tạo `TestAdministrativeShiftCheckinRepair` trong `test_data_repair.py`, mock truy vấn Frappe và `frappe.db.set_value`:

```python
def test_dry_run_reports_linked_old_metadata_without_writing(self):
	self.assertEqual(result["rows_to_update"], 1)
	self.assertEqual(result["linked_rows"], 1)
	set_value.assert_not_called()

def test_execute_updates_only_shift_metadata_and_preserves_modified(self):
	self.assertEqual(
		set(values),
		{"shift_start", "shift_end", "shift_actual_start", "shift_actual_end", "offshift"},
	)
	self.assertEqual(values["shift_end"], datetime(2026, 10, 6, 16, 30))
	self.assertEqual(values["shift_actual_end"], datetime(2026, 10, 6, 17, 30))
	self.assertEqual(values["offshift"], 0)
	self.assertFalse(set_value.call_args.kwargs["update_modified"])

def test_query_starts_at_effective_date_and_excludes_cancelled_rows(self):
	self.assertEqual(filters["time"], [">=", datetime(2026, 10, 1)])
	self.assertEqual(filters["docstatus"], ["<", 2])

def test_missing_shift_start_uses_checkin_calendar_date(self):
	self.assertEqual(values["shift_start"], datetime(2026, 10, 7, 7, 30))

def test_existing_shift_start_date_wins_over_checkin_time_date(self):
	self.assertEqual(values["shift_start"], datetime(2026, 10, 6, 7, 30))

def test_wrong_shift_master_aborts_before_query_or_write(self):
	with self.assertRaises(frappe.ValidationError):
		repair_administrative_shift_checkins(dry_run=False)

def test_already_correct_rows_are_idempotent(self):
	self.assertEqual(result["rows_to_update"], 0)
	self.assertEqual(result["already_correct"], 1)
	set_value.assert_not_called()
```

- [ ] **Step 2: Chạy test để xác nhận thất bại vì interface chưa tồn tại**

Run: `cd /home/snd/frappe-bench/apps/vinatex && /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_data_repair -v`

Expected: FAIL do chưa import được `repair_administrative_shift_checkins`.

- [ ] **Step 3: Cài đặt `repair_administrative_shift_checkins(effective_from="2026-10-01", dry_run=True) -> dict`**

Trong `data_repair.py`, validate `Shift Type` bằng `get_time`; lấy Checkin với đúng filter trong test; tính bốn datetime từ ngày `shift_start` hoặc `time`; chỉ gọi `frappe.db.set_value("Employee Checkin", name, values, update_modified=False)` khi ít nhất một trong năm trường mục tiêu khác giá trị chuẩn. Không commit trong helper để Bench quản lý transaction và lỗi có thể rollback toàn bộ.

- [ ] **Step 4: Chạy test data repair đến khi đạt**

Run: `cd /home/snd/frappe-bench/apps/vinatex && /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_data_repair -v`

Expected: `Ran 7 tests` và `OK`.

- [ ] **Step 5: Chạy regression suite của attendance/shift**

Run: `cd /home/snd/frappe-bench/apps/vinatex && /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_attendance_processing vinatex.vnt_hr.doctype.vnt_attendance_confirm.test_vnt_attendance_confirm -v`

Expected: toàn bộ test PASS; không thay đổi hành vi pipeline Attendance hoặc quy tắc giữ dòng xác nhận.

### Task 2: Preflight, backup và baseline sản xuất

**Files:**
- No repository files modified.
- Create operational artifact: database backup dưới `/home/snd/frappe-bench/sites/hrmsnd.vinatex.com.vn/private/backups/`.

**Interfaces:**
- Consumes: helper từ Task 1; site `hrmsnd.vinatex.com.vn`.
- Produces: đường dẫn backup và baseline trước sửa cho Checkin, Attendance, VNT Attendance Confirm.

- [ ] **Step 1: Xác nhận master và dry-run repair**

Run: `cd /home/snd/frappe-bench && bench --site hrmsnd.vinatex.com.vn execute vinatex.vnt_hr.shift_management.data_repair.repair_administrative_shift_checkins --kwargs '{"effective_from":"2026-10-01","dry_run":true}'`

Expected: không lỗi guard; snapshot hiện tại dự kiến `matched_rows=4577`, `rows_to_update=4577`, `linked_rows=4396`. Nếu số khác do log mới, ghi số thực tế làm baseline; `rows_to_update` phải lớn hơn 0.

- [ ] **Step 2: Chụp baseline Attendance và phiếu xác nhận**

Run các SELECT trong phần `Phạm vi và hiện trạng` của spec, lưu kết quả vào biên bản thực thi. Expected theo snapshot: 2.400 Attendance chưa hủy (2.138 Present, 262 Absent, 17.398 giờ, late/early bằng 0); 3.771 dòng xác nhận, 0 dòng `confirm=1`, 1.553 `EARLY_EXIT` của Hành chính.

- [ ] **Step 3: Xác nhận dry-run Attendance là no-op**

Run: `cd /home/snd/frappe-bench && bench --site hrmsnd.vinatex.com.vn execute vinatex.vinatex.doctype.overrides.attendance.create_attendance_from_checkin --kwargs '{"from_date":"2026-10-01","to_date":"2026-11-04","dry_run":1}'`

Expected: `Số Checkin gán lại đúng ca=0`, `Số Attendance tạo mới=0`, `Số Attendance bổ sung giờ vào/ra=0`, `Số lỗi=0`. Nếu không còn là no-op, dừng trước Task 3 và điều tra thay vì ghi.

- [ ] **Step 4: Chụp dry-run kỳ vọng của VNT Attendance Confirm theo từng tháng**

Run `make_attendance_confirm(..., dry_run=1)` cho `2026-10-01..2026-10-31` và `2026-11-01..2026-11-04`.

Expected theo snapshot: tháng 10 có 2.459 bất thường, trong đó 1.245 về sớm; tháng 11 có 343 bất thường, trong đó 158 về sớm; tổng 2.802 dòng.

- [ ] **Step 5: Tạo database backup và xác nhận file tồn tại**

Run: `cd /home/snd/frappe-bench && bench --site hrmsnd.vinatex.com.vn backup`

Expected: exit code 0; output in đường dẫn database backup mới; `test -s <backup-path>` thành công. Không sang Task 3 nếu chưa có file backup đọc được.

### Task 3: Thực thi backfill và đối soát sau ghi

**Files:**
- No repository files modified.
- Modify production data: targeted `Employee Checkin` metadata and unresolved `VNT Attendance Confirm Item` rows only.

**Interfaces:**
- Consumes: helper đã kiểm thử và baseline/backup từ Task 2.
- Produces: Checkin nhất quán 07:30–16:30 từ 01/10/2026; phiếu xác nhận khớp các bất thường hiện hành.

- [ ] **Step 1: Chạy repair thật một lần**

Run: `cd /home/snd/frappe-bench && bench --site hrmsnd.vinatex.com.vn execute vinatex.vnt_hr.shift_management.data_repair.repair_administrative_shift_checkins --kwargs '{"effective_from":"2026-10-01","dry_run":false}'`

Expected: `updated_rows == rows_to_update` của dry-run ngay trước đó; không có traceback.

- [ ] **Step 2: Chạy lại dry-run để chứng minh idempotent**

Run lại lệnh Task 2 Step 1 với `dry_run=true`.

Expected: `rows_to_update=0`, `already_correct=matched_rows`.

- [ ] **Step 3: Làm mới phiếu xác nhận tháng 10 và tháng 11**

Run lần lượt:

```bash
bench --site hrmsnd.vinatex.com.vn execute vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm --kwargs '{"from_date":"2026-10-01","to_date":"2026-10-31","dry_run":0}'
bench --site hrmsnd.vinatex.com.vn execute vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm --kwargs '{"from_date":"2026-11-01","to_date":"2026-11-04","dry_run":0}'
```

Expected: không lỗi; các phiếu hiện hữu được cập nhật, không sinh Attendance.

- [ ] **Step 4: Đối soát Checkin và Attendance**

Run lại baseline SQL. Expected: mọi Checkin mục tiêu có `shift_start=07:30`, `shift_end=16:30`, `shift_actual_start=06:30`, `shift_actual_end=17:30`, `offshift=0`; số lượng/liên kết Checkin không đổi. Attendance vẫn đúng baseline về tổng, trạng thái, tổng giờ và late/early.

- [ ] **Step 5: Đối soát phiếu xác nhận**

Run dry-run tháng 10 và tháng 11 lần nữa, rồi group các dòng đang lưu theo `issue_code` và `planned_shift`.

Expected theo snapshot: dữ liệu lưu khớp dry-run 2.802 dòng; tổng giảm đúng 969; `EARLY_EXIT` của Hành chính còn 584; không mất bất kỳ dòng `confirm=1` nào.

- [ ] **Step 6: Kiểm tra lỗi và ghi biên bản hoàn tất**

Kiểm tra Error Log tạo từ lúc bắt đầu Task 3 với tiêu đề/trace chứa `repair_administrative_shift_checkins`, `make_attendance_confirm` hoặc `VNT Attendance`. Expected: không có lỗi mới. Ghi lại thời điểm chạy, file backup, kết quả repair và ba nhóm checksum trước/sau.


# Grace Period 3 Minutes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vào muộn hoặc về sớm từ 3 phút trở xuống được tính là đúng giờ ở mọi ca, nên hiện `X` và không sinh phiếu giải trình.

**Architecture:** Một hằng số cấp module trong `attendance_processing.py` làm **sàn** cho dung sai của Shift Type: `max(cint(shift_doc.<field>), GRACE_PERIOD_MINUTES)`. Mọi nơi tính late/early đều đi qua `calculate_attendance_details`, nên sửa một chỗ là nhất quán; chi tiết nơi nào chịu ảnh hưởng (gọi với `respect_marking_flags=False`) và nơi nào không nằm trong phần Ràng buộc của spec.

**Tech Stack:** Python (Frappe v15), `unittest` chạy bằng `/home/snd/frappe-bench/env/bin/python`.

**Spec:** `docs/superpowers/specs/2026-10-28-grace-period-3-minutes-design.md`

## Global Constraints

- Ngưỡng là **3 phút**, đặt một lần duy nhất bằng hằng số `GRACE_PERIOD_MINUTES = 3` trong `vinatex/vnt_hr/attendance_processing.py`; không hằng số thứ hai ở nơi khác.
- Là **sàn**, không phải giá trị thay thế: Shift Type để 5 phút thì ca đó vẫn 5 phút.
- Biên nghiêm ngặt giữ nguyên: đúng 3:00 phút là **đúng giờ**, 3:01 mới tính muộn/sớm.
- `respect_marking_flags=True` phải giữ nguyên hành vi cũ: marking tắt → `late_entry`/`early_exit` luôn False, bất kể dung sai.
- Không sửa dữ liệu Shift Type, không bật `Enable Auto Attendance`, không đụng bản ghi Attendance đã lưu.
- Không commit trong task: cây làm việc đang có nhiều thay đổi chưa commit khác của phiên. Commit khi người dùng yêu cầu.

## Review Focus

- Ca có dung sai lớn hơn 3 (ví dụ 5 phút): sàn không được hạ xuống 3 (test ở Task 1, bước 1).
- Biên chính xác 3:00 so với 3:01 — khác nhau một giây quyết định `X` hay `Tr`/`Sm` (test ở Task 1, bước 1).
- Ca đêm vắt qua nửa đêm (`end_datetime` thuộc ngày hôm sau): dung sai phải cộng/trừ trên datetime chứ không phải giờ trong ngày (test ở Task 1, bước 1).
- Chỉ có giờ vào, không có giờ ra: `early_exit` phải là False, sàn không được biến nó thành True (test ở Task 1, bước 1).
- `respect_marking_flags=True` với marking tắt: vẫn False, sàn không được bật cờ lên (test ở Task 1, bước 1).

---

### Task 1: Sàn dung sai 3 phút trong `calculate_attendance_details`

**Files:**
- Modify: `vinatex/vnt_hr/attendance_processing.py` (hằng số cấp module; `calculate_attendance_details`, hiện ở dòng 340–405)
- Test: `vinatex/vnt_hr/shift_management/test_attendance_processing.py`

**Interfaces:**
- Consumes: helper sẵn có trong file test — `_window(start, end, *, work_date=date(2026, 10, 6), late=0, early=0, enable_marking=1, mode=...)` và `_log(value, log_type="")`.
- Produces: `GRACE_PERIOD_MINUTES = 3` (int, cấp module) trong `vinatex/vnt_hr/attendance_processing.py`; hành vi mới của `calculate_attendance_details(window, logs, *, respect_marking_flags=True)`.

- [ ] **Step 1: Viết các test thất bại**

Thêm vào `TestAttendanceProcessing` trong `test_attendance_processing.py`. Ca gốc dùng `_window(time(6), time(14), late=0, early=0, enable_marking=0)` và gọi với `respect_marking_flags=False`:

```python
def test_three_minute_grace_is_on_time_for_every_shift(self):
	# 6:02 vào, 13:58 ra -> trong ngưỡng
	self.assertFalse(details.late_entry)
	self.assertFalse(details.early_exit)

def test_exactly_three_minutes_is_still_on_time(self):
	# 6:03:00 và 13:57:00
	self.assertFalse(details.late_entry)
	self.assertFalse(details.early_exit)

def test_one_second_past_the_grace_is_late_and_early(self):
	# 6:03:01 và 13:56:59
	self.assertTrue(details.late_entry)
	self.assertTrue(details.early_exit)

def test_shift_grace_larger_than_three_minutes_still_wins(self):
	# late=5, early=5; 6:04 và 13:56 -> vẫn đúng giờ
	self.assertFalse(details.late_entry)
	self.assertFalse(details.early_exit)

def test_overnight_shift_grace_crosses_midnight(self):
	# _window(time(22), time(6)); vào 22:02 ngày 6/10, ra 5:58 ngày 7/10
	self.assertFalse(details.late_entry)
	self.assertFalse(details.early_exit)

def test_missing_out_punch_is_never_early_exit(self):
	# chỉ một log 6:02 -> early_exit False, has_out False
	self.assertFalse(details.early_exit)
	self.assertFalse(details.has_out)

def test_grace_floor_does_not_mark_when_marking_is_disabled(self):
	# enable_marking=0, respect_marking_flags mặc định True, vào 7:00 (muộn 1 tiếng)
	self.assertFalse(details.late_entry)
	self.assertFalse(details.early_exit)
```

- [ ] **Step 2: Chạy test để chắc chắn thất bại đúng chỗ**

Run: `cd /home/snd/frappe-bench/apps/vinatex && /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_attendance_processing -v 2>&1 | tail -20`
Expected: FAIL ở `test_three_minute_grace_is_on_time_for_every_shift` và `test_exactly_three_minutes_is_still_on_time` (hiện dung sai 0 nên 2–3 phút đã bị tính là muộn/sớm). Các test còn lại đạt ngay — đó là phần hành vi phải **giữ nguyên**.

- [ ] **Step 3: Thêm hằng số và sàn dung sai**

Trong `vinatex/vnt_hr/attendance_processing.py`: khai báo `GRACE_PERIOD_MINUTES = 3` cạnh các hằng số cấp module sẵn có, kèm một dòng giải thích vì sao ngưỡng nằm trong code chứ không trong Shift Type (xem spec). Trong `calculate_attendance_details`, thay `cint(shift_doc.late_entry_grace_period)` và `cint(shift_doc.early_exit_grace_period)` bằng `max(cint(...), GRACE_PERIOD_MINUTES)`. Giữ nguyên toán tử so sánh và phần `respect_marking_flags`. Sửa docstring: dung sai là `max` của Shift Type và sàn 3 phút.

- [ ] **Step 4: Chạy lại để chắc chắn đạt**

Run: `cd /home/snd/frappe-bench/apps/vinatex && /home/snd/frappe-bench/env/bin/python -m unittest vinatex.vnt_hr.shift_management.test_attendance_processing -v 2>&1 | tail -6`
Expected: PASS toàn bộ, gồm cả hai test sẵn có `test_report_mode_detects_late_and_early_without_auto_attendance` và `test_report_mode_treats_grace_boundaries_as_on_time`.

- [ ] **Step 5: Chạy các suite chịu ảnh hưởng gián tiếp**

Run: `cd /home/snd/frappe-bench/apps/vinatex/vinatex/vnt_hr/report && /home/snd/frappe-bench/env/bin/python -m unittest discover -s . -p "test_*.py" -t /home/snd/frappe-bench/apps/vinatex 2>&1 | tail -3`
Expected: `OK` (38 test) — ký hiệu `Tr`/`Sm` và phiếu giải trình đều tính qua hàm vừa sửa.

- [ ] **Step 6: Restart bench cho code Python có hiệu lực**

Run: `kill -TERM $(pgrep -f "gunicorn.*frappe.app:application" | tr '\n' ' '); sleep 8; curl -s -H "Host: hrmsnd.vinatex.com.vn" http://127.0.0.1:8000/api/method/ping`
Expected: `{"message":"pong"}` và `pgrep` cho ra PID mới.

- [ ] **Step 7: Đối chiếu trên dữ liệu thật**

Run: `cd /home/snd/frappe-bench && bench --site hrmsnd.vinatex.com.vn execute vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm --kwargs "{'from_date': '2026-10-01', 'to_date': '2026-10-27', 'dry_run': 1}"`
Expected: chạy xong không lỗi và in ra bảng đếm; ghi lại số **"Ngày làm việc về sớm"** để so với lần chạy trước khi sửa (phải giảm hoặc bằng, không được tăng). `dry_run=1` nên không ghi gì vào database. Việc dọn thật các dòng `Sm` cũ do HR tự bấm
**"Cập nhật giải trình"**; plan này không ghi gì vào phiếu giải trình.

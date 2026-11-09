# Cập nhật hồi tố ca Hành chính 16:30 — thiết kế ngắn

Ngày duyệt: 2026-11-05

## Mục đích và lý do

Shift Type `Hành chính` đã được Administrator đổi từ `07:30–17:00` sang
`07:30–16:30`. Quy định mới có hiệu lực từ **01/10/2026**; dữ liệu chấm công từ
ngày đó phải nhất quán với giờ kết thúc 16:30, nhưng không được làm thay đổi bằng
chứng chấm công gốc hoặc kết quả Attendance không liên quan đến giờ kết thúc ca.

## Phạm vi và hiện trạng

- Phạm vi hồi tố bắt đầu tại `2026-10-01 00:00:00`; không sửa bản ghi trước mốc này.
- Shift Type hiện đã đúng: bắt đầu 07:30, kết thúc 16:30, nhận check-in trước ca 60
  phút và cho phép check-out sau ca 60 phút.
- Tại thời điểm khảo sát có 4.577 Employee Checkin của ca Hành chính từ mốc hiệu
  lực. Cả 4.577 vẫn lưu `shift_end=17:00`; 3.942 lưu cửa sổ cũ 06:30–18:00 và 635
  lưu cửa sổ cũ 07:30–17:00. Có 4.396 bản ghi đã liên kết Attendance.
- Có 2.400 Attendance chưa hủy của ca Hành chính trong 01/10–04/11: 2.138 Present,
  262 Absent, tổng 17.398 giờ. Dry-run của pipeline Attendance báo **0** bản ghi cần
  sửa sau khi đổi giờ ca.
- Có 3.771 dòng VNT Attendance Confirm chưa hủy trong 01/10–04/11, tất cả chưa xác
  nhận. Tính lại theo 16:30 làm mất đúng 969 cảnh báo `EARLY_EXIT` của ca Hành chính;
  còn 2.802 bất thường hợp lệ, trong đó 584 cảnh báo về sớm của ca Hành chính vẫn còn.

Các con số trên là snapshot để đối soát; bước thực thi phải chụp lại baseline ngay
trước khi ghi vì log ngày hiện tại có thể tăng thêm.

## Goals

- Mọi Employee Checkin chưa hủy của ca Hành chính từ 01/10/2026 có metadata ca
  07:30–16:30 và cửa sổ thực tế 06:30–17:30.
- Làm mới phiếu VNT Attendance Confirm theo từng tháng để xóa các cảnh báo về sớm
  chưa xác nhận đã hết hiệu lực và giữ các bất thường vẫn đúng.
- Giữ nguyên thời gian quẹt thẻ, loại IN/OUT, liên kết Attendance, trạng thái và giờ
  công của Attendance.
- Có dry-run, backup và số liệu trước/sau để thao tác có thể kiểm tra và phục hồi.

## Non-goals

- Không thay đổi Shift Assignment, Employee.default_shift hoặc lịch kíp; chúng tham
  chiếu tên Shift Type và tự dùng giờ mới.
- Không sửa Employee Checkin trước 01/10/2026.
- Không bật HRMS Auto Attendance, không thay đổi các ngưỡng giờ công.
- Không tự động xác nhận hoặc điền giải trình cho bất thường còn lại.
- Không sửa hoặc xóa bản ghi Attendance.

## Anti-goals

- Không dùng một câu SQL rộng thiếu dry-run hoặc thiếu kiểm tra cấu hình Shift Type.
- Không ghi đè thời gian quẹt thẻ gốc hay trường `attendance` trên Employee Checkin.
- Không xóa dòng giải trình đã được HR xác nhận; cơ chế refresh hiện tại phải tiếp
  tục giữ dòng `confirm=1` làm dấu vết kiểm toán.
- Không coi việc pipeline Attendance dry-run trả về 0 là đã sửa metadata Checkin:
  pipeline hiện bỏ qua cập nhật ca trên Checkin đã liên kết Attendance.

## Approaches

1. **Data repair idempotent trong Frappe + dùng API refresh sẵn có — đã chọn.** Mở
   rộng `shift_management/data_repair.py` với dry-run, kiểm tra cấu hình ca, cập nhật
   đúng bốn trường thời gian ca trên Checkin, rồi gọi `make_attendance_confirm` riêng
   cho tháng 10 và tháng 11. Cách này kiểm thử được, chạy lại an toàn và có thống kê.
2. **UPDATE SQL trực tiếp.** Nhanh nhưng dễ sửa nhầm phạm vi/ngày, không tự bảo vệ khi
   Shift Type sai và khó kiểm thử; không phù hợp với dữ liệu chấm công đã trình.
3. **Chỉ chạy lại `create_attendance_from_checkin`.** Dry-run thực tế trả về 0 thay đổi
   và không sửa metadata của 4.396 Checkin đã liên kết; không đạt mục tiêu.

## Quyết định kỹ thuật

- Thêm `repair_administrative_shift_checkins(effective_from="2026-10-01",
  dry_run=True)` vào `vinatex/vnt_hr/shift_management/data_repair.py`; hàm không
  whitelist và chỉ chạy bằng `bench execute` sau backup.
- Hàm phải dừng trước khi ghi nếu `Hành chính` không đúng 07:30–16:30 hoặc hai buffer
  không đúng 60 phút.
- Chỉ chọn Employee Checkin có `shift="Hành chính"`, `time >= effective_from` và
  `docstatus < 2`. Ngày ca lấy từ `shift_start.date()` khi có, nếu thiếu mới lấy từ
  `time.date()`; ca Hành chính không qua đêm.
- Giá trị chuẩn cho từng ngày: `shift_start=07:30`, `shift_end=16:30`,
  `shift_actual_start=06:30`, `shift_actual_end=17:30`, `offshift=0`.
- Không thay đổi `time`, `log_type`, `attendance`, `skip_auto_attendance`, `employee`
  hoặc `modified`; cập nhật bằng `frappe.db.set_value(..., update_modified=False)`.
- Refresh VNT Attendance Confirm theo hai khoảng cùng tháng: 01/10–31/10 và
  01/11–04/11. Không chạy Attendance write pass vì dry-run đã chứng minh không có
  trường Attendance nào cần sửa.
- Trước khi ghi phải chạy `bench --site hrmsnd.vinatex.com.vn backup` và giữ đường dẫn
  file backup trong biên bản thực thi.

## Tiêu chí hoàn thành

- Dry-run repair và lần chạy thật báo cùng số `rows_to_update`; chạy dry-run lần hai
  sau sửa báo 0.
- Không còn Checkin thuộc phạm vi có bốn mốc ca khác 07:30/16:30/06:30/17:30 hoặc
  `offshift=1`.
- Các checksum Attendance trước/sau (số lượng theo trạng thái, tổng giờ, cờ
  late/early) giống hệt nhau.
- Sau refresh, số bất thường theo từng `issue_code` khớp dry-run; ở snapshot hiện tại
  tổng dòng giảm 969, chỉ nhóm `EARLY_EXIT` của ca Hành chính giảm từ 1.553 xuống 584.
- Không có lỗi mới trong Error Log liên quan đến data repair hoặc refresh xác nhận công.


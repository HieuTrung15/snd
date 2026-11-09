# Dung sai 3 phút cho đi muộn / về sớm — thiết kế ngắn

Ngày duyệt: 2026-10-28

## Mục đích và lý do

Lệch 1–2 phút ở máy vân tay không phải chuyện phải giải trình. Hiện cả 6 Shift Type
(Hành chính, Sáng, Chiều, Đêm, Đi ca, Vệ sinh) để `late_entry_grace_period` và
`early_exit_grace_period` bằng 0, nên:

- vào trễ 1 phút → ký hiệu `Tr` trên báo cáo tháng;
- ra sớm 1 phút → ký hiệu `Sm` **và** một dòng `EARLY_EXIT` trong phiếu VNT Attendance
  Confirm, tức bắt nhân sự giải trình.

Hai trường dung sai đó có sẵn trên form Shift Type nhưng bị ẩn sau ba lớp `depends_on`
(`enable_auto_attendance`, `enable_late_entry_marking`, `enable_early_exit_marking`).
Muốn nhìn thấy ô để gõ số thì phải bật `Enable Auto Attendance`, mà bật nó là giao việc
chấm công tự động cho job theo giờ của HRMS
(`hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts`), chạy
song song với `process_attendance` của app này.

Vì vậy ngưỡng 3 phút được đặt bằng code, như một luật chung của mọi ca.

## Goals

- Mọi ca có dung sai tối thiểu 3 phút cho cả hai vế (vào muộn và về sớm).
- Vào muộn/về sớm trong ngưỡng thì hiển thị `X` và không sinh phiếu giải trình.

## Non-goals

- Không bật `Enable Auto Attendance`.
- Không sửa dữ liệu Shift Type.
- Không đụng các bản ghi Attendance đã lưu.
- Không thêm doctype cấu hình.

## Anti-goals

- Nuốt mất dung sai lớn hơn mà HR đã gõ vào form Shift Type.
- Để luật lệch nhau giữa báo cáo tháng và lúc sinh phiếu giải trình.
- Xoá mất dòng giải trình HR đã quyết định.

## Ràng buộc

- Sửa đúng một chỗ: `calculate_attendance_details` trong
  `vinatex/vnt_hr/attendance_processing.py` (hiện ở dòng 368–378). Các nơi gọi, đã kiểm
  từng chỗ trong code:
  - `respect_marking_flags=False` nên **chịu ảnh hưởng của sàn**: hai báo cáo tháng
    (`report/monthly_report_common.py`, `report/tổng_hợp_chấm_công_tháng/monthly_symbols.py`),
    `_detect_confirmation_issue` trong `doctype/vnt_attendance_confirm/vnt_attendance_confirm.py`,
    và hai chỗ trong `api/leadership_dashboard.py` (danh sách đi trễ / về sớm của hôm qua).
  - `respect_marking_flags=True` (mặc định) nên **không chịu ảnh hưởng**: `process_attendance`
    (đường ghi Attendance) và `report/vnt_daily_attendance/vnt_daily_attendance.py`. Vì cả 6
    Shift Type đều tắt `enable_*_marking`, hai cờ ở đó vốn đã luôn False từ trước — báo cáo
    chấm công ngày hiển thị theo cờ đã lưu trong Attendance, không theo luật tính lại.
- Phép so sánh là nghiêm ngặt (`>` cho giờ vào, `<` cho giờ ra), nên **đúng 3:00 phút vẫn
  là đúng giờ, 3:01 mới tính muộn**. Dữ liệu vân tay có phần giây nên ngưỡng tính theo
  giây thật.
- `respect_marking_flags=True` (đường đi của `process_attendance`) phải giữ nguyên hành
  vi cũ: marking tắt thì `late_entry`/`early_exit` luôn False.

## Approaches

1. **Sàn tối thiểu `max(dung sai của ca, 3)`** — *đã chọn*: vừa là luật chung cho mọi ca,
   vừa không phớt lờ con số lớn hơn ai đó gõ vào form.
2. Hằng số thay thế hoàn toàn, bỏ qua hai trường của Shift Type — đơn giản hơn nhưng nuốt
   lặng cấu hình người khác đặt.
3. So 3 phút ở `_get_symbol` và `_detect_confirmation_issue` — phải chép cùng một luật ra
   2–3 chỗ, chắc chắn lệch nhau theo thời gian.

## Quyết định

- Hằng số cấp module `GRACE_PERIOD_MINUTES = 3` trong `attendance_processing.py`, dùng cho
  cả hai vế qua `max(cint(shift_doc.<field>), GRACE_PERIOD_MINUTES)`.
- Cập nhật docstring của `calculate_attendance_details` cho đúng hành vi mới.
- Sau khi sửa phải restart bench (Python chạy dưới gunicorn `--preload`).
- HR bấm **"Cập nhật giải trình"** để dọn các dòng `Sm` dưới 3 phút chưa ai quyết định;
  `_upsert_employee_confirmation` chỉ xoá dòng chưa `confirm`, dòng HR đã xác nhận giữ lại
  làm dấu vết.

## Còn lại cho người làm

Vị trí đặt hằng số trong file và cách diễn đạt docstring.

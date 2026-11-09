# Thiết kế hồi tố kíp Trần Hữu Phúc từ 01/11/2026

> **Đã được thay thế:** Thiết kế repair một nhân sự này được mở rộng thành `2026-11-05-safe-backdated-shift-group-transfer-design.md`. Không triển khai tài liệu này độc lập.

## Ý định

Sửa lịch kíp của `NMSVNĐ00073` — Trần Hữu Phúc — từ kíp `6` sang kíp `1`, hiệu lực `01/11/2026` đến `31/12/2026`, đồng thời đưa ca kế hoạch, Checkin, Attendance và phiếu giải trình về cùng một nguồn sự thật.

## Quyết định nghiệp vụ đã chốt

- Punch `01/11/2026 05:59:29` tiếp tục thuộc Attendance ca Đêm ngày `31/10/2026` (`HR-ATT-2026-05291`).
- Attendance ngày 31/10 và hai Checkin liên kết `31/10 13:55:53`, `01/11 05:59:29` không được thay đổi.
- Ngày 01/11 áp dụng ca Sáng của kíp `1`, chỉ có punch OUT `14:13:25`; kết quả là `Absent`, thiếu IN và vẫn cần giải trình.
- Ngày 02–04/11 được tính lại theo kíp `1`: Chiều, Chiều, Đêm. Ca Đêm ngày 04/11 được phép dùng punch `05/11 05:52:25` vì đó là giờ kết thúc của ngày công 04/11.
- Không tạo hoặc chốt Attendance cho ngày công 05/11 vì ngày đó chưa hoàn tất tại thời điểm sửa.

## Phương án

1. **Bỏ chặn hồi tố trong công cụ hàng loạt:** không chọn vì sẽ mở khả năng sửa ngược dữ liệu đã chấm công cho mọi nhân sự.
2. **Chỉ sửa membership:** không chọn vì Shift Assignment và Attendance 01–04/11 vẫn thuộc kíp `6`, khiến báo cáo mâu thuẫn.
3. **Repair một lần, khóa đúng nhân sự và kỳ dữ liệu:** chọn. Repair có preview, guard dữ liệu nguồn, dry-run mặc định, thực thi nguyên tử và verify độc lập.

## Luồng sửa

1. Xác minh đúng Employee, membership kíp `6`, cấu hình kíp `1`, ba Attendance 02–04/11, 52 Shift Assignment tự động kíp `6`, và chưa có quyết định HR trên các dòng giải trình 01–04/11.
2. Hủy ba Attendance 02–04/11 bằng API Document để Checkin được bỏ liên kết nhưng các chứng từ cũ vẫn giữ trạng thái Cancelled làm lịch sử.
3. Chuyển ba Shift Assignment lịch sử 02–04/11 sang đúng ca/kíp đích bằng repair có audit; không xóa chứng từ.
4. Kết thúc membership kíp `6` vào 31/10 và tạo membership kíp `1` từ 01/11 đến 31/12; bảo đảm trường hiển thị Employee vẫn là `Theo kíp`/`1`.
5. Tạo ca và chạy attendance cho 01–04/11. Punch 05:59 vẫn bị giữ bởi Attendance 31/10; punch 05:52 ngày 05/11 được sở hữu bởi ca Đêm ngày 04/11.
6. Hủy các Shift Assignment tự động kíp `6` chưa sử dụng từ 05/11 trở đi, rồi sinh lịch kíp `1` đến 31/12.
7. Refresh phiếu giải trình tháng 11 riêng cho nhân sự này.

## Kết quả bắt buộc

- Membership: kíp `6` kết thúc 31/10; kíp `1` hiệu lực 01/11–31/12, không chồng lấn.
- Có đúng 53 ngày có Shift Assignment kíp `1` trong 01/11–31/12, khớp ma trận kíp `1`; thứ Sáu là OFF.
- Attendance 31/10 và punch 05:59 không đổi từng trường.
- Ba Attendance cũ 02–04/11 ở trạng thái Cancelled; bốn Attendance mới 01–04/11 được submit.
- 01/11: Sáng, Absent, không có IN, OUT `14:13:25`.
- 02/11: Chiều, Present, `14:03:01`–`21:54:04`.
- 03/11: Chiều, Present, `13:57:31`–`22:08:09`.
- 04/11: Đêm, Present, `21:55:39`–`05/11 05:52:25`.
- Phiếu giải trình tháng 11 chỉ còn bất thường 01/11 `MISSING_IN` trong phạm vi 01–04/11.
- Không thay đổi số lượng hoặc thời gian thô của Employee Checkin; không tạo Attendance ngày 05/11.

## An toàn và audit

- Không sửa API đổi kíp hàng loạt; quy tắc cấm backdate chung vẫn giữ nguyên.
- Repair không nhận Employee/kíp/ngày tùy ý; các hằng số được khóa theo yêu cầu này.
- `preview()` và `execute(dry_run=True)` chỉ đọc. `execute(dry_run=False)` chạy sau backup và kiểm tra lại toàn bộ guard ngay trước khi ghi.
- Nếu dữ liệu nguồn thay đổi, xuất hiện Attendance/Checkin mới hoặc có quyết định HR, repair dừng trước lần ghi đầu tiên.
- Lần chạy thứ hai trả về `ALREADY_APPLIED` và không phát sinh thay đổi.
- Không commit hoặc push; mã và bằng chứng giữ trên `develop` local theo cách làm đã thống nhất.

## Ngoài phạm vi

- Không cho phép hồi tố hàng loạt cho nhân sự khác.
- Không tạo punch giả hoặc dùng một punch cho hai Attendance.
- Không xóa chứng từ Attendance/Shift Assignment để che lịch sử.
- Không sửa Attendance hoặc giải trình tháng 10.


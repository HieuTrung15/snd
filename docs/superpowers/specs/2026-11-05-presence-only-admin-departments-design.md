# Thiết kế giải trình chỉ theo cặp IN/OUT cho hai công đoạn

## Ý định

Nhân sự thuộc `Vào bông - NMSVNĐ` hoặc `Công đoạn Đóng gói - NMSVNĐ` vẫn có ca kế hoạch `Hành chính`, nhưng giờ làm thực tế không tuân theo mốc 07:30–16:30. Với nhóm này, phiếu giải trình chỉ phản ánh việc thiếu dữ liệu vào/ra, không đánh giá đi muộn, về sớm, thời lượng làm việc hoặc chấm ngoài khung giờ Hành chính.

## Quy tắc đã duyệt

- Chỉ áp dụng khi Department hiện tại của Employee thuộc một trong hai Department trên và ca kế hoạch của ngày là `Hành chính`.
- Chỉ đánh giá ngày đã kết thúc theo ngày của site; ngày hiện tại và tương lai không được kết luận. Vì vậy cặp `06:02 IN`, `06:02 OUT` của ngày 05/11 chỉ là dữ liệu đang tích lũy và chưa được xử lý trong ngày 05/11.
- Với ngày làm việc đã kết thúc, gộp mọi Checkin thuộc ngày đó, không phân biệt nằm trong hay ngoài khung 07:30–16:30:
  - Không có Checkin: tạo `WORKDAY_NO_CHECKIN`.
  - Có IN nhưng không có OUT: tạo `MISSING_OUT`.
  - Có OUT nhưng không có IN: tạo `MISSING_IN`.
  - Có ít nhất một IN và một OUT: không tạo giải trình; không áp dụng khoảng cách tối thiểu giữa hai lần chấm.
- Ngày OFF tiếp tục dùng quy tắc hiện tại; có chấm công ngày OFF vẫn cần HR xác nhận.
- Ngày lễ và các Department/ca khác giữ nguyên cách xử lý hiện tại.
- Không sửa Employee Checkin hoặc Attendance. Thay đổi chỉ ảnh hưởng việc phát hiện và đồng bộ phiếu `VNT Attendance Confirm`.
- Khi chạy lại dữ liệu cũ, dòng chưa xác nhận không còn phù hợp sẽ bị loại bỏ; dòng đã HR xác nhận tiếp tục được giữ làm lịch sử.

## Các hướng đã cân nhắc

1. **Danh sách Department cố định trong mã — chọn.** Phù hợp đúng hai đơn vị đã nêu, không thêm trường cấu hình hoặc thao tác dữ liệu chủ. Đổi tên Department sẽ cần cập nhật mã.
2. **Checkbox cấu hình trên Department.** Linh hoạt hơn nhưng cần thay đổi schema, migrate và quản trị cấu hình; chưa cần thiết cho phạm vi hai Department cố định.
3. **Checkbox trên từng Employee.** Cho phép ngoại lệ cá nhân nhưng dễ sai lệch khi điều chuyển nhân sự và không phản ánh đúng quy tắc theo Department.

## Mục tiêu và giới hạn

Thành công là sau khi đồng bộ lại, hai Department chỉ còn giải trình ngày làm việc cho `WORKDAY_NO_CHECKIN`, `MISSING_IN`, `MISSING_OUT`, cùng các cảnh báo ngày OFF vốn có. Không thay đổi ký hiệu công, cách tính lương, dữ liệu máy chấm công hoặc quy tắc của nhân sự khác.

# Đồng bộ Holiday List khi chuyển từ kíp sang Hành chính

## Mục tiêu

Khi HR chuyển một Employee từ kíp hiện tại sang nhóm `HC`, hồ sơ Employee phải đồng bộ đầy đủ dữ liệu hiển thị của lịch Hành chính. Ngoài `custom_shift_group = HC` và `custom_working_schedule_type = Hành chính`, trường `holiday_list` phải lấy từ `VNT Shift Group HC` (hiện là `2026`). Điều này tránh việc hồ sơ vẫn giữ Holiday List của kíp cũ và gây sai lệch ở các phân hệ đọc trực tiếp Employee Holiday List.

## Phạm vi

- Áp dụng cho mọi điểm vào đang dùng workflow chuyển kíp chung: hồ sơ Employee, Employee List và chuyển hồi tố.
- Chỉ thay đổi Holiday List khi nhóm đích là `HC`; các lần chuyển sang nhóm khác giữ nguyên hành vi hiện tại.
- Dùng `VNT Shift Group.holiday_list` làm nguồn dữ liệu, không mã hóa cứng tên `2026`.
- Nếu nhóm `HC` không có Holiday List, giao dịch phải dừng với thông báo rõ ràng; không để trạng thái chuyển dở dang.
- Không tự động chuyển dữ liệu của Employee nào nếu HR chưa thực hiện lệnh chuyển kíp.

## Thiết kế

Mở rộng dịch vụ đồng bộ cache Employee hiện có. Sau khi xác định membership đang hiệu lực, nếu nhóm đích là `HC`, dịch vụ đọc Holiday List của nhóm và cập nhật nguyên tử ba trường `custom_shift_group`, `custom_working_schedule_type`, `holiday_list`. Vì cả workflow thường và hồi tố đều gọi dịch vụ này trong giao dịch chuyển kíp, quy tắc được áp dụng nhất quán mà không lặp mã ở giao diện.

Preview phải kiểm tra cấu hình Holiday List của `HC` trước khi cho phép thực hiện, để lỗi cấu hình được hiển thị trước khi thay đổi dữ liệu.

## Phương án đã xem xét

1. **Chỉ đồng bộ khi nhóm đích là `HC` — được chọn.** Đúng phạm vi yêu cầu và ít ảnh hưởng các luồng hiện có.
2. Đồng bộ Holiday List cho mọi nhóm đích. Nhất quán rộng hơn nhưng thay đổi hành vi ngoài phạm vi đã duyệt.
3. Chạy tác vụ sửa Holiday List sau chuyển. Bị loại vì có thể tạo trạng thái dữ liệu không đồng bộ giữa hai bước.

## Kiểm thử chấp nhận

- Employee có `holiday_list = KIP-01-2026`, membership Kíp 1, khi chuyển sang HC được cập nhật thành `holiday_list = 2026` cùng với hai trường cache lịch làm việc.
- Preview/execute bị chặn nếu nhóm HC không cấu hình Holiday List.
- Chuyển sang nhóm không phải HC không thay đổi Holiday List của Employee.
- Các bài kiểm thử workflow thường, hồi tố và UI hiện có vẫn đạt.
- Kiểm tra chỉ đọc trên Trần Thị Đỉnh (`NMSVNĐ00105`) vẫn trả về `READY` trước khi HR thực hiện chuyển chính thức.

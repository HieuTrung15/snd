# Thiết kế xóa phiếu giải trình chấm công rỗng

## Mục tiêu

Phiếu `VNT Attendance Confirm` không còn dòng `items` không có ý nghĩa nghiệp vụ, phải được xóa và không được tính là nhân sự còn cần giải trình chấm công.

## Quy tắc nghiệp vụ

- Khi đồng bộ loại bỏ dòng bất thường chưa được HR xác nhận cuối cùng, xóa phiếu cha thay vì lưu phiếu rỗng.
- Dòng đã được HR xác nhận phải được giữ làm lịch sử; phiếu còn ít nhất một dòng đã xác nhận không được xóa.
- Khi không có phiếu cũ và cũng không có bất thường, không tạo phiếu mới.
- Kết quả đồng bộ trả thêm `Số phiếu đã xóa` để giao diện và tác vụ nền báo cáo đúng.
- Nếu thao tác làm mới ngay trên một phiếu khiến chính phiếu đó bị xóa, giao diện phải quay về danh sách thay vì tải lại tài liệu đã mất.
- Dọn toàn bộ phiếu rỗng hiện có bằng Frappe document API sau khi sao lưu và xác minh không có dòng chi tiết.

## Phạm vi dữ liệu đã kiểm tra

Ngày 2026-11-05 có 17 phiếu chưa hủy không có dòng chi tiết. Không phiếu nào có tệp đính kèm, bình luận hoặc trao đổi. Phiếu mẫu `GTCC-NMSVNĐ00175-2026-11` thuộc Nguyễn Thị Oanh nằm trong tập này.

## Ngoài phạm vi

- Không thay đổi cách phát hiện ngày bất thường.
- Không xóa phiếu còn bất kỳ dòng chi tiết nào.
- Không thay đổi dữ liệu Checkin hoặc Attendance.

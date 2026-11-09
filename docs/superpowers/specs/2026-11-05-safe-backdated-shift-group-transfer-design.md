# Thiết kế chuyển kíp hồi tố an toàn trên màn hình Employee

## Ý định

Cho phép HR chuyển kíp với ngày hiệu lực trong quá khứ ngay tại dialog **Phân / chuyển kíp hàng loạt**, áp dụng cho bất kỳ Employee và VNT Shift Group hợp lệ nào, đồng thời sửa nhất quán membership, ca kế hoạch, Attendance và phiếu giải trình mà không sửa log thời gian thô.

Trường hợp đầu tiên phải áp dụng sau triển khai là `NMSVNĐ00073` — Trần Hữu Phúc — chuyển từ kíp `6` sang kíp `1` từ `01/11/2026`.

## Phương án

1. **Bỏ điều kiện cấm backdate trong service hiện tại:** loại bỏ vì luồng hiện tại chủ động chặn mọi Checkin/Attendance và không có cơ chế rebuild lịch sử.
2. **Công cụ repair chỉ Administrator dùng bằng lệnh:** an toàn nhưng không đáp ứng yêu cầu HR thao tác trên màn hình hiện tại.
3. **Nhánh hồi tố riêng trong dialog hiện tại:** chọn. Ngày hiện tại/tương lai tiếp tục dùng service cũ; ngày quá khứ gọi backend hồi tố có preview token, blocker, xác nhận mạnh, audit và transaction riêng.

## Trải nghiệm người dùng

- Dialog giữ các trường hiện có: Kíp mới, Ngày hiệu lực, Ngày kết thúc, Lý do/Ghi chú.
- Khi Ngày hiệu lực nhỏ hơn ngày hiện tại, hiển thị banner đỏ **Chuyển kíp hồi tố sẽ tính lại dữ liệu chấm công đã có**.
- Chỉ HR Manager và System Manager được preview/thực hiện hồi tố; HR User vẫn dùng luồng ngày hiện tại/tương lai.
- Preview hồi tố hiển thị theo từng Employee:
  - kíp nguồn và kíp đích;
  - Attendance sẽ cancel/tạo lại;
  - ca tự động lịch sử sẽ sửa hoặc chuyển OFF;
  - ca tương lai sẽ cancel/tạo lại;
  - punch qua ranh giới được giữ cho ngày công trước;
  - phiếu giải trình sẽ refresh;
  - blocker và lý do.
- Nút thực hiện chỉ xuất hiện khi toàn batch `READY`. Người dùng phải nhập đúng `XÁC NHẬN HỒI TỐ` sau preview.
- Preview sinh `preview_token`; execute từ chối nếu dữ liệu, lịch, membership hoặc request thay đổi sau preview.

## Phân tách backend

- Service chuyển kíp hiện tại giữ nguyên cho ngày hiện tại/tương lai và tiếp tục từ chối backdate.
- Module hồi tố mới cung cấp:
  - `preview_backdated_shift_group_transfer(...) -> dict`
  - `execute_backdated_shift_group_transfer(..., preview_token, confirmation_text) -> dict`
- Planner thuần nhận request + snapshot và trả action plan; phần truy vấn/ghi Frappe tách khỏi quyết định nghiệp vụ để test không cần production database.
- Một batch tối đa 20 Employee, tối đa 366 ngày và all-or-nothing. “Bất kỳ nhân sự nào” nghĩa là không khóa mã Employee; mỗi lần vẫn chuyển các Employee đã chọn sang cùng một kíp đích như dialog hiện tại.

## Quy tắc preview và blocker

Một Employee bị `BLOCKED` nếu có một trong các điều kiện:

- nhiều membership Active chồng ngày hiệu lực hoặc membership tương lai chồng kỳ;
- Company không khớp kíp đích hoặc kíp không có lịch/Shift Type hợp lệ;
- Shift Assignment manual/legacy trong khoảng phải thay thế;
- Attendance có Leave Application, Attendance Request, On Leave, Work From Home hoặc nguồn không thể chứng minh là kết quả pipeline;
- dòng VNT Attendance Confirm đã có quyết định HR trong khoảng phải tính lại;
- Salary Slip đã submit bao phủ khoảng Attendance phải tính lại;
- punch/Attendance/assignment bị thay đổi giữa preview và execute;
- batch vượt giới hạn hoặc request không nằm trong hiệu lực của kíp đích.

Attendance `Present`, `Absent` hoặc `Half Day` không gắn Leave/Attendance Request được phép rebuild khi thuộc ca tự động nguồn. Ngày không có Attendance vẫn được planner xử lý từ Checkin hiện hữu.

Để chứng minh nguồn, Attendance do `process_attendance` tạo mới từ phiên bản này mang marker read-only `custom_vnt_generated_by_pipeline = 1` và link `custom_vnt_source_shift_assignment`. Attendance legacy chưa có marker chỉ được rebuild khi có ít nhất một Checkin liên kết, ca trùng một Shift Assignment mang đủ marker tự động và không có dấu hiệu leave/request; Attendance legacy không có Checkin bị block vì không thể phân biệt chắc chắn với bản ghi nhập tay.

## Ranh giới punch và ngày hoàn tất

- Employee Checkin là log thô: không tạo, xóa hoặc sửa `time`/`log_type`.
- Punch đã liên kết một Attendance có `attendance_date < effective_date` được giữ nguyên toàn bộ liên kết và không tái sử dụng.
- Punch sau 00:00 của ca Đêm thuộc ngày công trước vẫn được dùng nếu ca đó đã kết thúc.
- Chỉ rebuild work date từ ngày hiệu lực đến ngày hôm qua; không tạo/chốt Attendance cho work date hôm nay hoặc tương lai.
- Nếu đã có Attendance cho work date hôm nay, hoặc Checkin hôm nay được xác định thuộc work date hôm nay, Employee bị block. Checkin hôm nay được phép dùng duy nhất khi nó đã liên kết ngày công trước hoặc planner chứng minh nó là đuôi ca Đêm đã kết thúc của ngày công trước.
- Metadata ca và liên kết Attendance trên các punch thuộc kỳ rebuild được phép cập nhật bằng pipeline chuẩn.

## Attendance và Shift Assignment lịch sử

1. Cancel Attendance đủ điều kiện bằng Document API; bản ghi Cancelled được giữ làm audit và Checkin được unlink qua hook chuẩn.
2. Shift Assignment mang đủ marker `Kíp tự động` được sửa theo lịch kíp đích:
   - ngày làm: cập nhật ca/kíp nguồn của assignment lịch sử và ghi Comment chứa operation id + before snapshot;
   - ngày OFF: hủy assignment tự động bằng helper kiểm soát, chỉ sau khi mọi Attendance cùng Employee/ngày đã Cancelled và không còn Checkin liên kết Attendance đó; giữ before snapshot trong Comment. Do HRMS `ShiftAssignment.on_cancel` vẫn chặn cả Attendance đã Cancelled, helper này được phép chuyển chính xác auto assignment đã guard sang `docstatus = 2`, `status = Inactive` bằng DB update có `modified/modified_by`; đây là nơi duy nhất được bypass hook.
3. Assignment manual/legacy không bao giờ tự sửa; preview trả blocker.
4. Ca tự động chưa sử dụng từ ngày hiện tại trở đi dùng cancel/generate chuẩn.
5. Sau khi plan ngày đúng, chạy `process_attendance` theo từng tháng/khoảng ngày hoàn tất và refresh VNT Attendance Confirm theo từng tháng.

## Membership và transaction

- Employee rows được khóa theo thứ tự ổn định.
- Execute dựng lại snapshot dưới lock, so `preview_token`, rồi mới ghi lần đầu.
- Membership nguồn kết thúc vào ngày trước effective date; membership đích Active được tạo tới membership_end_date. Không sửa `Employee.default_shift`.
- Phiên bản đầu yêu cầu `membership_end_date >= today`. Hồi tố một kỳ đã kết thúc cần biết membership kế tiếp và nằm ngoài luồng này; request như vậy bị từ chối thay vì tạo khoảng trống lịch sau ngày kết thúc.
- `Employee.custom_working_schedule_type` và `custom_shift_group` được cập nhật để hiển thị kíp hiện tại sau khi toàn transaction thành công.
- Toàn batch chạy một transaction; một lỗi rollback mọi Employee.
- Mỗi Employee nhận Comment audit có operation id, người thực hiện, lý do, request và summary trước/sau. Membership note cũng mang operation id.
- Chạy lại cùng request trên trạng thái đích trả `ALREADY_APPLIED`, không tạo dữ liệu trùng.

## An toàn quyền và tải

- Backend kiểm tra role; ẩn UI không thay thế authorization.
- Backdate không chạy queue trong phiên bản đầu: tối đa 20 Employee để transaction, preview token và lỗi được xử lý đồng bộ.
- Request quá 500 employee-days vẫn được phép nếu không vượt 20 Employee/366 ngày, nhưng preview phải hiển thị quy mô; execute có timeout phù hợp và không commit từng dòng.
- Không sửa source `frappe`, `erpnext`, `hrms`.

## Trường hợp Trần Hữu Phúc

- Giữ nguyên Attendance `HR-ATT-2026-05291` ngày 31/10 và punch `EMP-CKIN-11-2026-000070` lúc 01/11 05:59:29.
- Kíp `6` kết thúc 31/10; kíp `1` hiệu lực 01/11–31/12.
- 01/11: Sáng, `Absent`, thiếu IN, OUT 14:13:25; confirmation `MISSING_IN`.
- 02/11: Chiều, `Present`, 14:03:01–21:54:04.
- 03/11: Chiều, `Present`, 13:57:31–22:08:09.
- 04/11: Đêm, `Present`, 21:55:39–05/11 05:52:25.
- Không tạo Attendance work date 05/11 trong lần hồi tố này.

## Ngoài phạm vi

- Không tự sửa manual Shift Assignment, leave, Attendance Request, Salary Slip hoặc quyết định HR đã duyệt.
- Không cho một punch thuộc hai Attendance và không tạo punch giả.
- Không thay đổi luồng chuyển kíp ngày hiện tại/tương lai.
- Không hỗ trợ nhiều kíp đích trong một batch.


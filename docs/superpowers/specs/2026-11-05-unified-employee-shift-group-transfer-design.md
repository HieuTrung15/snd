# Thiết kế chuyển kíp thống nhất từ Employee Form và Employee List

## Mục tiêu

HR có thể đổi kíp cho một Employee ngay trên hồ sơ Employee hoặc cho một/nhiều Employee từ Employee List bằng cùng một quy trình có ngày hiệu lực, preview và xác nhận. Sau khi thực hiện, membership, ca kế hoạch, Attendance đã hoàn tất và phiếu giải trình phải nhất quán với kíp mới; không được lưu riêng trường `Employee.custom_shift_group` làm lệch dữ liệu.

Trường hợp đầu tiên cần xử lý sau triển khai là `NMSVNĐ00092` — Đinh Văn Sỹ — chọn kíp `3`, ngày hiệu lực `01/11/2026`.

## Phương án đã chọn

Ba hướng đã được cân nhắc:

1. Viết một dialog và backend riêng cho Employee Form: ít sửa code hiện tại nhưng nhân đôi quy tắc, dễ làm Form và List cho kết quả khác nhau.
2. Chỉ tái sử dụng JavaScript của List: giao diện giống nhau nhưng client vẫn phải tự chọn hai backend, còn API/server không có một hợp đồng thống nhất.
3. Dùng một facade backend và một dialog dùng chung cho Form/List: chọn. Facade định tuyến sang engine thường hoặc hồi tố theo ngày hiệu lực; cả hai màn hình gửi cùng request và nhận cùng cấu trúc kết quả.

## Nguồn dữ liệu chuẩn

- `VNT Shift Group Assignment` là nguồn chính để xác định kíp của Employee tại một ngày.
- `Employee.custom_shift_group` là cache hiển thị “Kíp hiện tại”, phản ánh membership Active bao phủ ngày hiện tại; đây không phải nguồn để ghi lịch sử chuyển kíp.
- Khi có membership hợp lệ, mọi preview phải hiển thị kíp nguồn từ membership. Nếu cache Employee khác membership, preview phải báo rõ `display_mismatch` và execution đồng bộ lại cache, không tạo membership đích trùng.
- Nếu chưa có membership bao phủ ngày hiện tại, job đồng bộ không tự xóa cache legacy; nó trả trạng thái `SKIPPED_NO_ACTIVE_MEMBERSHIP` để tránh làm mất dữ liệu cũ ngoài phạm vi chuyển đổi.
- `Employee.default_shift` không bị sửa bởi quy trình này.

## Luồng trên Employee Form

1. Chỉ áp dụng cho hồ sơ Employee đã lưu. Hồ sơ mới phải được lưu trước khi phân/chuyển kíp.
2. Khi HR chọn giá trị mới ở `custom_shift_group`, client lập tức đưa field về giá trị đã lưu; giá trị mới chỉ được dùng để mở dialog chuyển kíp.
3. Nếu form còn thay đổi chưa lưu ngoài field kíp, không mở workflow; báo HR lưu hoặc hủy các thay đổi đó trước để việc reload sau chuyển kíp không làm mất dữ liệu.
4. Dialog dùng cùng các field và quy tắc với Employee List: Kíp mới, Ngày hiệu lực, Ngày kết thúc thuộc kíp, Tạo ca đến ngày và Lý do/Ghi chú. Kíp mới được điền sẵn từ giá trị HR vừa chọn.
5. HR bấm Xem trước, kiểm tra tác động, rồi xác nhận. Backdate vẫn bắt buộc HR Manager/System Manager, preview token còn hiệu lực và chuỗi `XÁC NHẬN HỒI TỐ`.
6. Hủy dialog hoặc preview bị chặn không thay đổi Employee hay dữ liệu chấm công.
7. Sau execution thành công, form reload từ server. Nếu ngày hiệu lực là tương lai, “Kíp hiện tại” vẫn hiển thị kíp đang có hiệu lực và tự chuyển vào ngày hiệu lực; thông báo kết quả phải nói rõ đây là thay đổi đã lên lịch.
8. Backend từ chối thay đổi trực tiếp `custom_shift_group` trên một Employee hiện hữu bằng `doc.save()`/REST nếu không đi qua workflow; UI không phải lớp bảo vệ duy nhất.

## Luồng trên Employee List

- Action `Phân / chuyển kíp hàng loạt` tiếp tục nhận một hoặc nhiều Employee đã chọn.
- List dùng chính dialog và facade backend giống Form; không tự duy trì bản sao field, validation hoặc renderer preview.
- Một request chỉ có một kíp đích. Batch là all-or-nothing: một Employee bị blocker thì không ghi Employee nào.
- Với ngày hiện tại/tương lai, membership và ca kế hoạch được ghi ngay theo hiệu lực; không tính lại Attendance lịch sử.
- Với ngày quá khứ, engine hồi tố tính lại các work date đã hoàn tất từ ngày hiệu lực tới tối đa ngày hôm qua, rồi refresh phiếu giải trình của các tháng liên quan.

## Hợp đồng backend thống nhất

Facade mới cung cấp:

- `preview_shift_group_transfer(employees, target_shift_group, effective_date, membership_end_date, generate_until=None, note=None) -> dict`
- `execute_shift_group_transfer(employees, target_shift_group, effective_date, membership_end_date, generate_until=None, note=None, preview_token=None, confirmation_text=None) -> dict`

Facade chuẩn hóa request tối thiểu, xác định mode bằng ngày hiện tại của server và gọi service hiện có:

- `effective_date < today`: backdated service;
- `effective_date >= today`: normal service.

Không dùng mode do browser gửi để tránh client ép nhầm engine. Các endpoint cũ được giữ để tương thích nhưng UI mới chỉ gọi facade.

Kết quả preview luôn có `mode`, `counts`, `rows`; kết quả execution luôn có `status`, `mode`, `employees`, `effective_date`, `target_shift_group`. Trường hợp hàng đợi vẫn trả `QUEUED` và phát realtime event hiện có.

## Đồng bộ “Kíp hiện tại” theo ngày hiệu lực

- Helper dùng chung resolve đúng một membership Active bao phủ `as_of_date`; nhiều membership chồng nhau là lỗi, không âm thầm chọn một dòng.
- Sau normal/backdated execution, helper đồng bộ cache cho các Employee trong request theo ngày hiện tại.
- Chuyển hôm nay hoặc hồi tố cập nhật cache sang kíp đích ngay sau transaction thành công.
- Chuyển tương lai giữ cache ở kíp nguồn cho tới ngày hiệu lực.
- Daily shift scheduler chạy bước đồng bộ cache trước khi sinh ca kế hoạch để chuyển cache đúng ngày và để generator đọc dữ liệu nhất quán.
- Mọi cập nhật cache của workflow dùng DB-level controlled write, không gọi lại validation chống sửa trực tiếp trên Employee.

## Attendance, phiếu giải trình và dữ liệu hôm nay

- Employee Checkin là log thô: không tạo, xóa hoặc sửa `time`/`log_type`.
- Engine hồi tố chỉ rebuild Attendance từ ngày hiệu lực đến `today - 1`; không tạo/chốt Attendance cho work date hôm nay.
- Attendance có work date hôm nay vẫn là blocker vì quy trình hôm nay chưa kết thúc.
- Checkin của hôm nay được giữ và không block chỉ khi planner chứng minh đồng thời:
  - target schedule hôm nay là ngày làm và có Shift Type hợp lệ;
  - có đúng một Shift Assignment Active bao phủ hôm nay;
  - assignment đó mang đủ marker kíp tự động;
  - `custom_shift_group` và `shift_type` của assignment đúng bằng target plan hôm nay;
  - planner không tạo action cancel/rewrite/generate cho assignment hôm nay.
- Nếu thiếu assignment, assignment manual/legacy, kíp/ca khác target, ngày target OFF, hoặc dữ liệu hôm nay sẽ phải thay đổi thì giữ blocker `CURRENT_WORK_DATE_DATA`.
- Punch đuôi ca Đêm của ngày công hôm trước tiếp tục theo quy tắc đã có.
- Sau rebuild, `VNT Attendance Confirm` được refresh theo từng tháng; dòng có quyết định HR vẫn là blocker.

## Blocker và an toàn giữ nguyên

- Manual/legacy Shift Assignment cần thay thế.
- Membership Active chồng lấn hoặc membership tương lai xung đột.
- Leave, Attendance Request, Attendance nguồn bảo vệ/không chứng minh được provenance.
- Phiếu giải trình đã có kết quả HR.
- Submitted Salary Slip bao phủ kỳ rebuild.
- Preview token hết hiệu lực do dữ liệu hoặc request thay đổi.
- Company/kỳ hiệu lực/kích thước batch không hợp lệ.
- Dữ liệu hôm nay không thỏa điều kiện giữ nguyên ở trên.

Execution khóa dữ liệu, dựng lại preview dưới lock và ghi trong một transaction. Không bỏ qua blocker chỉ vì thao tác đến từ Employee Form hoặc vì batch chỉ có một người.

## Trường hợp Đinh Văn Sỹ

Baseline hiện quan sát được: cache `Employee.custom_shift_group` hiển thị `4`, trong khi membership/ca kế hoạch có hiệu lực đã thể hiện kíp `3`; punch `05/11/2026 05:56:31` thuộc dữ liệu hôm nay làm preview cũ bị `CURRENT_WORK_DATE_DATA`.

Với request target `3`, effective `01/11/2026`, end/generate `31/12/2026`:

- preview phải lấy kíp hiện hành theo membership và báo cache hiển thị lệch;
- không tạo thêm membership kíp `3` nếu dòng đích hợp lệ đã tồn tại;
- punch hôm nay được giữ nếu assignment hôm nay đã đúng kíp/ca target và không có action hôm nay;
- chỉ Attendance/confirmation của `01/11–04/11/2026` được tính lại;
- `custom_shift_group` được sửa thành `3` sau thành công;
- raw punch hôm nay và quy trình chấm công ngày `05/11` không bị kết thúc sớm.

Nếu snapshot production không đúng baseline này, dừng trước write và báo lại thay vì suy diễn dữ liệu nguồn.

## Ngoài phạm vi

- Không cho chọn nhiều kíp đích trong cùng batch.
- Không tự sửa manual Shift Assignment, leave, Attendance Request, Salary Slip hoặc quyết định HR.
- Không thay đổi `Employee.default_shift` và không tạo punch giả.
- Không tự động chuyển Employee mới chưa lưu; HR lưu hồ sơ trước rồi chạy workflow.
- Không commit hoặc push; toàn bộ thay đổi tiếp tục nằm trên branch `develop` local hiện tại.

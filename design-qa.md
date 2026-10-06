# Design QA — Home

- Source visual truth: ảnh Home người dùng đính kèm trong hội thoại.
- Source pixel dimensions: `1714 × 834` px.
- Implementation: Custom HTML Block `Trang chủ tổng hợp` trong workspace `/app/home` trên site `hrmsnd.vinatex.com.vn`.
- Implementation screenshot path: chưa có. Môi trường hiện tại không có browser tool hoặc phiên Frappe đã đăng nhập để chụp trang.
- Viewport mục tiêu: desktop `1714 × 834` px; giao diện sáng; ngày `24/09/2026`.
- Density normalization: chưa áp dụng vì chưa có browser-rendered implementation capture.

**Findings**

- [P1] Chưa thể hoàn tất đối chiếu pixel bằng ảnh render.
  - Location: toàn bộ workspace Home.
  - Evidence: có ảnh nguồn và implementation đã đồng bộ lên site, nhưng chưa có ảnh implementation sau đăng nhập để ghép cùng ảnh nguồn.
  - Impact: chưa thể xác nhận trực quan chiều cao hàng, vị trí lịch, wrapping chữ và khoảng cách với sidebar ở đúng viewport.
  - Fix: chụp Home sau đăng nhập tại viewport tương ứng, ghép hai ảnh trong cùng comparison input và xử lý mọi P1/P2 còn lại.

**Required Fidelity Surfaces**

- Fonts and typography: dùng font stack của Frappe/Inter; nhãn KPI `9px`, tiêu đề `14px`, số KPI `24px`, nội dung lối tắt `10.5px`. Đã kiểm tra tĩnh, chưa xác minh antialiasing/wrapping bằng ảnh render.
- Spacing and layout rhythm: hàng KPI 4 cột cao `100px`, hàng công việc/bản tin cao `306px`, hàng tiện ích/lịch cao `376px`, gap `12px`, radius `14–16px` theo ảnh nguồn.
- Colors and visual tokens: nền `#f5f8fb`, navy `#1d247c`, cyan `#0e7898`, viền xanh `#b9d8f7`, thẻ ngày `#f6f6f7`, hôm nay `#dff3ff`.
- Image quality and assets: ảnh nguồn không có raster content; icon lấy từ Font Awesome 4 có sẵn trong `desk.bundle.css`, không dùng placeholder.
- Copy and content: 4 KPI, hai khối feed, 14 lối tắt, lịch chung/cá nhân và chú giải khớp nội dung ảnh nguồn.

**Interaction And Data Checks**

- KPI tiếp tục lấy từ ba report chấm công và API phép năm hiện có.
- Công việc lấy từ `get_my_todos`; bản tin lấy từ `get_vnt_news`; lịch lấy từ `get_department_calendar`.
- Nút xem danh sách, KPI, lối tắt, tab lịch và điều hướng tháng đều có hành vi thực.
- JavaScript syntax, Python compile, Custom HTML Block sync, Workspace binding và sự tồn tại của các report/DocType đích đã được kiểm tra.
- Console errors, hover/focus, responsive và browser-rendered primary interactions: chưa kiểm tra được do thiếu browser session.

**Comparison History**

- Lần 1: blocked trước browser-rendered comparison vì không có implementation screenshot sau đăng nhập.

**Implementation Checklist**

- [x] Gom Home thành một composition ổn định theo đúng ba hàng trong ảnh.
- [x] Giữ dữ liệu thật và trạng thái rỗng; không thêm số liệu mẫu.
- [x] Bổ sung đủ nội dung và lối tắt còn thiếu.
- [x] Đồng bộ Custom HTML Block và Workspace lên site.
- [ ] Chụp trang đã đăng nhập và hoàn tất vòng so sánh pixel.

final result: blocked

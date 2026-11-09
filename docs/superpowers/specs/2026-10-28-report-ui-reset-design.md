# Dọn giao diện báo cáo cũ khi đổi query-report — thiết kế ngắn

Ngày duyệt: 2026-10-28

## Mục đích và lý do

Trang `query-report` của Frappe dùng chung **một** instance `frappe.query_report`
cho mọi báo cáo. Khi đổi từ báo cáo này sang báo cáo khác:

- `$status` (vùng `message`: dải "Màu cần giải trình", chú thích ký hiệu) chỉ
  được ẩn khi **dữ liệu báo cáo mới đã về** (`hide_status()` nằm trong `.then()`
  của `refresh`), tức sau 2 lượt gọi server cộng 2–3,5 s chạy truy vấn.
- Bảng ma trận của *Tổng hợp chấm công tháng* được chèn **ngoài** `$report`
  (`insertAfter(report.$report)`), nên datatable mới dựng lại không ghi đè nó.
- Class `vnt-attendance-html-mode` đặt trên `report.page.main` kèm luật
  `.report-wrapper { display: none !important; }` còn nguyên khi sang báo cáo
  khác, ẩn luôn bảng của báo cáo mới.

Hệ quả: người dùng thấy giao diện báo cáo trước trên trang báo cáo đang mở, phải
chờ tải xong (hoặc F5) mới đúng.

## Mốc nghiệm thu

Không còn thấy giao diện cũ **kể từ lúc báo cáo mới bắt đầu tải**. Không yêu cầu
"sạch tức thì khoảnh khắc bấm chuột" như một mục tiêu riêng.

## Goals

- Mọi query-report — kể cả báo cáo chuẩn của Frappe và báo cáo tự dựng sau này —
  vào trang là sạch: không còn chú thích, bảng HTML hay class ẩn datatable của
  báo cáo trước.

## Non-goals

- Không đổi cách ba báo cáo dựng bảng.
- Không đụng tới file Excel xuất ra.

## Anti-goals

- Làm hỏng Export / Print / Auto-Email (vẫn dựa vào datatable bị ẩn).
- Làm mất màn hình "Loading".
- Xoá mất giao diện tự dựng khi người dùng **đổi bộ lọc trong cùng một báo cáo**.

## Ràng buộc

- `$status`, `$summary`, `$chart`, `$loading`, `$report`, `$message` đều là phần
  tử **anh em** trong `page.main` (xem `setup_report_wrapper`), nên `$report.empty()`
  không ảnh hưởng màn hình chờ.
- App đã có sẵn `vinatex/public/js/report_actions_override.js` vá
  `frappe.views.QueryReport.prototype` theo đúng kiểu cần dùng (vòng chờ tới khi
  class tồn tại, cờ `_vnt_*_patched`).
- `/assets/vinatex` là symlink tới `vinatex/public`, nên file tĩnh có hiệu lực
  ngay; chỉ cần restart bench cho thay đổi trong `hooks.py`.

## Approaches

1. **Vá ở cấp app qua `app_include_js`** — *đã chọn*. Đây là vấn đề của trang
   query-report chứ không của riêng báo cáo nào; vá ở prototype nên có tác dụng
   ngay từ lần điều hướng đầu tiên, và báo cáo tự dựng tiếp theo được hưởng luôn.
   Đổi lại: sửa `hooks.py` + restart, và là script toàn cục.
2. Teardown lặp trong ba file report — không đụng `hooks.py`, nhưng ~20 dòng lặp
   ba chỗ và chỉ chạy sau khi đã vào một trong ba báo cáo trong phiên.
3. Đưa mọi thứ vào trong `$report` để vòng đời Frappe tự dọn — sạch nhất về kiến
   trúc nhưng diff lớn nhất, đụng cả Python, và chú thích biến mất lúc chờ tải.

## Quyết định

- File mới `vinatex/public/js/report_ui_reset.js`, thêm vào `app_include_js` kèm
  `?v={version}`; vá `QueryReport.prototype.load_report`, chạy phần dọn **trước**
  khi gọi bản gốc.
- Nội dung dọn: `$status.empty().hide()`, `$report.empty()`, xoá mọi phần tử
  `[data-vnt-report-ui]` trong `page.main`, gỡ mọi class trên `page.main` kết thúc
  bằng `-html-mode`.
- Hợp đồng chung: phần tử tự dựng nằm ngoài `$report` phải mang
  `data-vnt-report-ui`. Đánh dấu wrapper của *Tổng hợp chấm công tháng*; hai báo
  cáo kia đánh dấu luôn cho nhất quán.
- Chỉ vá `load_report` (chỉ chạy khi **đổi** báo cáo), không vá `refresh`, nhờ vậy
  đổi bộ lọc trong cùng báo cáo không bị xoá giao diện.
- Giữ nguyên bản vá `report.refresh` trong *Tổng hợp chấm công tháng* vì nó lo
  trường hợp đổi bộ lọc cùng báo cáo (datatable được tái sử dụng, không dựng lại).

## Còn lại cho người làm

Tên hằng và cờ guard trong file mới theo đúng kiểu `report_actions_override.js`.

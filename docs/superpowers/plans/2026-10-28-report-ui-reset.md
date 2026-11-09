# Report UI Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi đổi sang một query-report khác, trang không còn giữ lại chú thích, bảng HTML tự dựng hay class ẩn datatable của báo cáo trước.

**Architecture:** Một script cấp app (`app_include_js`) vá `frappe.views.QueryReport.prototype.load_report` — hàm chỉ chạy khi **đổi** báo cáo — và dọn các phần tử dùng chung của trang trước khi gọi bản gốc. Các giao diện tự dựng nằm ngoài `$report` tự khai báo mình qua thuộc tính `data-vnt-report-ui` để script dọn đúng chỗ mà không cần biết tên class của từng báo cáo.

**Tech Stack:** JavaScript thuần (IIFE, không bundler) trong `vinatex/public/js/`; Node 18 + `node:assert` cho test; `hooks.py` của Frappe.

**Spec:** `docs/superpowers/specs/2026-10-28-report-ui-reset-design.md`

## Global Constraints

- File trong `vinatex/public/js/` là JS thuần, IIFE, **không qua bundler**; `/assets/vinatex` là symlink tới `vinatex/public` nên **không cần `bench build`**.
- Mọi mục trong `app_include_js` phải kèm `?v={version}` (biến `version` đã có sẵn đầu `hooks.py`).
- Vá prototype phải theo kiểu `vinatex/public/js/report_actions_override.js`: vòng chờ `setTimeout(..., 200)` tới khi `frappe?.views?.QueryReport` tồn tại, và một cờ `_vnt_*_patched` chống vá hai lần.
- **Chỉ** vá `load_report`. Không vá `refresh` — đổi bộ lọc trong cùng một báo cáo phải giữ nguyên giao diện tự dựng.
- Không được làm hỏng Export / Print / Auto-Email (vẫn dựa vào datatable bị ẩn) và không được làm mất màn hình "Loading" (`$loading` là phần tử anh em của `$report`).
- Giữ nguyên bản vá `report.refresh` trong `tổng_hợp_chấm_công_tháng.js` (nó lo việc đổi bộ lọc trong cùng báo cáo, khi datatable được tái sử dụng chứ không dựng lại) — không gộp, không xoá.
- Test JS chạy bằng `node <file>`, không thêm dependency, không thêm `package.json`.
- Dự án hiện có nhiều thay đổi chưa commit không liên quan; **không commit** trong các task này. Commit khi người dùng yêu cầu.

## Review Focus

- Lần điều hướng đầu tiên vào một báo cáo: `load_report` chạy khi `$status`/`$report`/`page` có thể chưa tồn tại → không được ném lỗi (test ở Task 1, bước 1).
- Script được nạp hai lần (hot reload, hai tab asset): vá chồng khiến bản gốc chạy hai lần → cờ guard (test ở Task 1, bước 1).
- `frappe.views.QueryReport` chưa được định nghĩa lúc script chạy: phải chờ rồi vá, không im lặng bỏ qua (test ở Task 1, bước 1).
- Đổi bộ lọc trong cùng một báo cáo: `load_report` không chạy, `refresh` không bị vá → giao diện tự dựng còn nguyên (test ở Task 1, bước 1).
- `page.main` mang nhiều class, trong đó có class không phải chế độ hiển thị: chỉ được gỡ class kết thúc bằng `-html-mode`, giữ nguyên phần còn lại (test ở Task 1, bước 1).

---

### Task 1: Script dọn giao diện cấp app

**Files:**
- Create: `vinatex/public/js/report_ui_reset.js`
- Create: `vinatex/tests/js/report_ui_reset.test.js`
- Modify: `vinatex/hooks.py:45` (thêm một mục vào `app_include_js`, ngay sau `hide_workflow_help.js`)

**Interfaces:**
- Consumes: `frappe.views.QueryReport.prototype.load_report` (bản gốc của Frappe).
- Produces: hợp đồng DOM cho Task 2 — mọi phần tử giao diện tự dựng nằm ngoài `$report` phải mang thuộc tính `data-vnt-report-ui`; script xoá chúng bằng `page.main.find("[data-vnt-report-ui]").remove()`.

- [ ] **Step 1: Viết test thất bại**

`vinatex/tests/js/report_ui_reset.test.js` — nạp script bằng `vm.runInThisContext` với `global.frappe` giả, rồi gọi `load_report` trên một instance giả. Các khẳng định:

```js
// 1
test("dọn $status, $report, phần tử đánh dấu và class chế độ trước khi gọi bản gốc", ...)
assert.deepEqual(calls, ["status.empty", "status.hide", "report.empty", "custom.remove", "original"]);
assert.equal(main.classes(), "layout-main-section vnt-keep-me");
// 2
test("không ném lỗi khi $status/$report/page chưa tồn tại", ...)
assert.doesNotThrow(() => instance.load_report());
// 3
test("nạp script hai lần không vá chồng", ...)
assert.equal(original_calls, 1);
// 4
test("chờ tới khi frappe.views.QueryReport tồn tại rồi mới vá", ...)
assert.equal(typeof proto.load_report, "function");
assert.notEqual(proto.load_report, original_load_report);
// 5
test("không đụng tới refresh", ...)
assert.equal(proto.refresh, original_refresh);
```

Stub `$status`/`$report` cần `empty()` và `hide()` trả về chính nó; stub `page.main` cần `find()`, `remove()`, `attr("class")`, `removeClass()`. Test 4 đặt `global.frappe = {}` trước khi nạp rồi mới gán `frappe.views.QueryReport` và chờ quá 200 ms.

- [ ] **Step 2: Chạy test để chắc chắn nó thất bại**

Run: `node vinatex/tests/js/report_ui_reset.test.js`
Expected: FAIL — `Cannot find module` / không tìm thấy `report_ui_reset.js`.

- [ ] **Step 3: Viết `vinatex/public/js/report_ui_reset.js`**

IIFE, tab-indent, theo khuôn `report_actions_override.js`:

- hằng: `PATCH_FLAG = "_vnt_report_ui_reset_patched"`, `CUSTOM_UI_SELECTOR = "[data-vnt-report-ui]"`, `MODE_CLASS_SUFFIX = "-html-mode"`.
- `reset_report_ui(report)` → `undefined`: thoát sớm nếu thiếu `report`; `report.$status.empty().hide()`; `report.$report.empty()`; với `report.page.main`: `find(CUSTOM_UI_SELECTOR).remove()` rồi gỡ các class kết thúc bằng `MODE_CLASS_SUFFIX` (tách `attr("class")` theo `/\s+/`, lọc, `removeClass(list.join(" "))`). Mỗi thuộc tính đều phải kiểm tra tồn tại trước khi dùng.
- `patch_query_report()` → `undefined`: chờ `frappe?.views?.QueryReport` như file mẫu; đặt cờ; bọc `load_report` sao cho `reset_report_ui(this)` chạy **trước** `original_load_report.apply(this, arguments)` và trả về giá trị của bản gốc.

- [ ] **Step 4: Chạy test để chắc chắn nó đạt**

Run: `node vinatex/tests/js/report_ui_reset.test.js`
Expected: PASS — in ra đủ 5 dòng test đạt.

- [ ] **Step 5: Đăng ký script trong `hooks.py`**

Thêm `f"/assets/vinatex/js/report_ui_reset.js?v={version}",` vào cuối danh sách `app_include_js`, sau `hide_workflow_help.js`.

- [ ] **Step 6: Kiểm chứng cú pháp và đường dẫn phục vụ**

Run: `node --check vinatex/public/js/report_ui_reset.js && /home/snd/frappe-bench/env/bin/python -m py_compile vinatex/hooks.py && ls -l /home/snd/frappe-bench/sites/assets/vinatex/js/report_ui_reset.js`
Expected: không lỗi; `ls` in ra file (chứng tỏ symlink `/assets` đã phục vụ được, không cần build).

- [ ] **Step 7: Restart bench để `hooks.py` có hiệu lực**

Run: `kill -TERM $(pgrep -f "gunicorn.*frappe.app:application" | tr '\n' ' '); sleep 8; curl -s -H "Host: hrmsnd.vinatex.com.vn" http://127.0.0.1:8000/api/method/ping`
Expected: `{"message":"pong"}` và `pgrep` cho ra các PID mới.

---

### Task 2: Đánh dấu giao diện tự dựng của ba báo cáo

**Files:**
- Modify: `vinatex/vnt_hr/report/tổng_hợp_chấm_công_tháng/tổng_hợp_chấm_công_tháng.js` (hàm `getMatrixContainer`, chỗ tạo `vnt-attendance-matrix-wrapper`)
- Modify: `vinatex/vnt_hr/report/báo_cáo_công_hàng_tháng/báo_cáo_công_hàng_tháng.js` (`<section class="vnt-monthly-report" …>`)
- Modify: `vinatex/vnt_hr/report/báo_cáo_tăng_ca_hàng_tháng/báo_cáo_tăng_ca_hàng_tháng.js` (`<section class="vnt-overtime-report" …>`)
- Create: `vinatex/tests/js/report_ui_markers.test.js`

**Interfaces:**
- Consumes: hợp đồng `data-vnt-report-ui` do Task 1 định nghĩa.

- [ ] **Step 1: Viết test thất bại**

`vinatex/tests/js/report_ui_markers.test.js` — đọc ba file nguồn và khẳng định phần tử gốc của giao diện tự dựng mang thuộc tính đánh dấu:

```js
const CASES = [
  ["tổng_hợp_chấm_công_tháng/tổng_hợp_chấm_công_tháng.js", /class="vnt-attendance-matrix-wrapper"[^>]*data-vnt-report-ui/],
  ["báo_cáo_công_hàng_tháng/báo_cáo_công_hàng_tháng.js", /<section class="vnt-monthly-report"[^>]*data-vnt-report-ui/],
  ["báo_cáo_tăng_ca_hàng_tháng/báo_cáo_tăng_ca_hàng_tháng.js", /<section class="vnt-overtime-report"[^>]*data-vnt-report-ui/],
];
assert.match(source, pattern);
```

- [ ] **Step 2: Chạy test để chắc chắn nó thất bại**

Run: `node vinatex/tests/js/report_ui_markers.test.js`
Expected: FAIL — cả ba mẫu đều không khớp.

- [ ] **Step 3: Thêm thuộc tính `data-vnt-report-ui` vào ba phần tử gốc**

Chỉ thêm thuộc tính, không đổi class, style hay cấu trúc. Wrapper của báo cáo ma trận là phần tử **bắt buộc** (nằm ngoài `$report`); hai `<section>` kia đánh dấu cho nhất quán.

- [ ] **Step 4: Chạy test để chắc chắn nó đạt**

Run: `node vinatex/tests/js/report_ui_markers.test.js && node vinatex/tests/js/report_ui_reset.test.js`
Expected: PASS cả hai.

- [ ] **Step 5: Kiểm chứng cú pháp ba file report**

Run: `for f in vinatex/vnt_hr/report/*/*.js; do node --check "$f" || exit 1; done && echo ok`
Expected: `ok`.

- [ ] **Step 6: Kiểm tra tay trên site**

Hard-reload (Ctrl+Shift+R) rồi đi lần lượt: *Tổng hợp chấm công tháng* → *Báo cáo công hàng tháng* → *Báo cáo tăng ca hàng tháng* → một báo cáo chuẩn của Frappe → quay lại *Tổng hợp chấm công tháng*.
Expected: ở mỗi lần đổi, ngay khi báo cáo mới bắt đầu tải đã không còn chú thích/bảng của báo cáo trước; bảng của báo cáo mới hiện bình thường (không bị `vnt-attendance-html-mode` ẩn mất); đổi bộ lọc trong cùng một báo cáo vẫn giữ nguyên bảng tự dựng; "Tải xuống Excel" vẫn chạy.

/**
 * VNT Workspace Hub
 * -----------------------------------------------------------------------------
 * Vẽ lại giao diện của một số workspace (mặc định: "1.1 Tổ chức") theo phong cách
 * "trung tâm tiện ích": hero, khối số liệu, các panel nhóm chức năng.
 *
 * NGUYÊN TẮC:
 *  - KHÔNG sửa dữ liệu. Toàn bộ nội dung được đọc lại từ chính Workspace hiện tại
 *    (block content + page_data do Frappe trả về, đã lọc quyền sẵn).
 *  - KHÔNG đụng tới màn hình khác: chỉ can thiệp khi workspace có trong HUB_CONFIG.
 *  - Bấm "Edit" vẫn vào editor gốc bình thường; thoát Edit thì hub vẽ lại.
 *
 * Icon: Lucide (https://lucide.dev, MIT) — nhúng sẵn tập con cần dùng để không
 * phải tải thêm thư viện ngoài (tránh chớp giao diện và phụ thuộc mạng).
 */
(() => {
	"use strict";

	/* ======================================================================
	 * 1. ICON — tập con Lucide (24x24, stroke)
	 * ==================================================================== */
	const ICON_PATHS = {
		network:
			'<rect x="16" y="16" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="9" y="2" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/><path d="M12 12V8"/>',
		"circle-check-big":
			'<path d="M21.801 10A10 10 0 1 1 17 3.335"/><path d="m9 11 3 3L22 4"/>',
		"clipboard-check":
			'<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
		award:
			'<path d="m15.477 12.89 1.515 8.526a.5.5 0 0 1-.81.47l-3.58-2.687a1 1 0 0 0-1.197 0l-3.586 2.686a.5.5 0 0 1-.81-.469l1.514-8.526"/><circle cx="12" cy="8" r="6"/>',
		shuffle:
			'<path d="M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22"/><path d="m18 2 4 4-4 4"/><path d="M2 6h1.9c1.5 0 2.9.9 3.6 2.2"/><path d="M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8"/><path d="m18 14 4 4-4 4"/>',
		briefcase:
			'<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>',
		"arrow-left-right":
			'<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
		"building-2":
			'<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/>',
		"id-card":
			'<path d="M16 10h2"/><path d="M16 14h2"/><path d="M6.17 15a3 3 0 0 1 5.66 0"/><circle cx="9" cy="11" r="2"/><rect x="2" y="5" width="20" height="14" rx="2"/>',
		layers:
			'<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
		target:
			'<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
		users:
			'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
		"chart-column":
			'<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
		"calendar-check":
			'<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="m9 16 2 2 4-4"/>',
		"trending-up":
			'<path d="M16 7h6v6"/><path d="m22 7-8.5 8.5-5-5L2 17"/>',
		"user-check":
			'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m16 11 2 2 4-4"/>',
		landmark:
			'<path d="M10 18v-7"/><path d="M11.12 2.198a2 2 0 0 1 1.76.006l7.866 3.847c.476.233.31.949-.22.949H3.474c-.53 0-.695-.716-.22-.949z"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M3 22h18"/><path d="M6 18v-7"/>',
		"file-text":
			'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
		"layout-grid":
			'<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
		"arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
		"users-round":
			'<path d="M18 21a8 8 0 0 0-16 0"/><circle cx="10" cy="8" r="5"/><path d="M22 20c0-3.37-2-6.5-4-8a5 5 0 0 0-.45-8.3"/>',
		"contact-card":
			'<rect x="4" y="2" width="16" height="20" rx="2"/><circle cx="9.5" cy="10" r="1.8"/><path d="M6.8 16a2.8 2.8 0 0 1 5.4 0"/><path d="M15 8.5h3"/><path d="M15 12h3"/><path d="M15 15.5h2"/>',
		"book-open":
			'<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
		cake:
			'<path d="M20 21v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8"/><path d="M2 21h20"/><path d="M4 16h16"/><path d="M12 5v6"/><circle cx="12" cy="3" r="1.2"/>',
		building:
			'<path d="M3 21h18"/><path d="M6 21V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v14"/><path d="M12 3v2"/><path d="M9.5 10h.01"/><path d="M14.5 10h.01"/><path d="M9.5 14h.01"/><path d="M14.5 14h.01"/><path d="M11 21v-3h2v3"/>',
		calendar:
			'<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 15h5"/><path d="M8 18h3"/>',
		"file-chart":
			'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M8 17v-3"/><path d="M12 17v-7"/><path d="M16 17v-5"/>',
		"share-2":
			'<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.59 13.51 6.83 3.98"/><path d="m15.41 6.51-6.82 3.98"/>',
		"file-x":
			'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m14.5 12.5-5 5"/><path d="m9.5 12.5 5 5"/>',
		"triangle-alert":
			'<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
		"shield-alert":
			'<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
		"clipboard-list":
			'<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
		"refresh-cw":
			'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
		"user-round-plus":
			'<path d="M2 21a8 8 0 0 1 13.29-6"/><circle cx="10" cy="8" r="5"/><path d="M19 16v6"/><path d="M22 19h-6"/>',
		/* người kèm dấu "<" ">" — dùng cho cấp lãnh đạo (cấp cao / cấp trung) */
		"user-levels":
			'<circle cx="12" cy="8.5" r="3"/><path d="M18 19a6 6 0 0 0-12 0"/><path d="m5 6-2.5 2.5L5 11"/><path d="m19 6 2.5 2.5L19 11"/>',
	};

	const icon = (name) =>
		`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ` +
		`stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">` +
		`${ICON_PATHS[name] || ICON_PATHS["layout-grid"]}</svg>`;

	/* ======================================================================
	 * 2. CẤU HÌNH — mỗi workspace một entry
	 * ==================================================================== */

	/** Nhãn của item -> { t: tiêu đề hiển thị, i: icon } */
	const ITEM_META = {
		// --- Quyết định ---
		"Quyết định bổ nhiệm": { i: "circle-check-big" },
		"Quyết định giao nhiệm vụ": { i: "clipboard-check" },
		"Quyết định khen thưởng": { i: "award" },
		"Quyết định điều động bổ nhiệm": { i: "shuffle" },
		"Quyết định cử CB đi công tác": { i: "briefcase" },
		"Quyết định điều động": { i: "arrow-left-right" },
		// --- Danh mục nền tảng ---
		"Danh sách Ban chức năng": { i: "building-2" },
		"Danh sách Phòng/Ban": { i: "network" },
		"Danh sách Công ty/ ĐVTV": { i: "building-2" },
		"Danh sách chi nhánh": { i: "network" },
		"Sơ đồ tổ chức": { i: "network", route: "/app/vnt-organization-chart" },
		"Danh mục chức danh": { i: "id-card" },
		"Danh mục nhóm chức danh": { i: "layers" },
		"Quản lý định biên": { i: "target" },
		"Tình hình sử dụng lao động": {
			i: "users",
			route: "/app/query-report/BÁO CÁO TÌNH HÌNH SỬ DỤNG LAO ĐỘNG",
		},
		// --- Báo cáo ---
		"Báo cáo tình hình sử dụng lao động": { t: "Tình hình sử dụng lao động", i: "chart-column" },
		"Báo cáo định biên - thực tế": { t: "Định biên - thực tế", i: "target" },
		"Báo cáo danh sách cán bộ quy hoạch": {
			t: "Danh sách cán bộ quy hoạch",
			i: "calendar-check",
		},
		"Báo cáo cơ cấu lao động theo nhóm tuổi": {
			t: "Cơ cấu lao động theo nhóm tuổi",
			i: "chart-column",
		},
		"Báo cáo nhân viên theo chức danh": { t: "Nhân viên theo chức danh", i: "id-card" },
		"Báo cáo thống kê lao động theo vị trí công việc": {
			t: "Lao động theo vị trí công việc",
			i: "users",
		},
		"Báo cáo số liệu lao động theo phòng ban": { t: "Lao động theo phòng ban", i: "network" },
		"Báo cáo số liệu lao động theo nhóm nghề": { t: "Lao động theo nhóm nghề", i: "layers" },
		"Báo cáo thống kê biến động lao động": {
			t: "Thống kê biến động lao động",
			i: "trending-up",
		},
		"Báo cáo biến động cơ cấu tổ chức": { t: "Biến động cơ cấu tổ chức", i: "network" },
		"Báo cáo cán bộ được bổ nhiệm": { t: "Cán bộ được bổ nhiệm", i: "circle-check-big" },
		"Báo cáo cán bộ đến tuổi nghỉ hưu": { t: "Cán bộ đến tuổi nghỉ hưu", i: "user-check" },
	};

	/** Đoán icon cho item chưa khai báo, để thêm mới không bị "trống" */
	const ICON_RULES = [
		[/quyết định/i, "circle-check-big"],
		[/định biên/i, "target"],
		[/chức danh/i, "id-card"],
		[/nhóm/i, "layers"],
		[/phòng ban|ban chức năng|sơ đồ|cơ cấu tổ chức/i, "network"],
		[/công ty|đơn vị|doanh nghiệp|chi nhánh/i, "building-2"],
		[/nghỉ hưu|bổ nhiệm/i, "user-check"],
		[/biến động|tăng giảm/i, "trending-up"],
		[/lao động|nhân viên|cán bộ|nhân sự/i, "users"],
		[/báo cáo|thống kê|số liệu/i, "chart-column"],
		[/hợp đồng|văn bản|hồ sơ/i, "file-text"],
	];

	const HUB_CONFIG = {
		"1.1 Tổ chức": {
			hero: {
				icon: "network",
				title: "Trung tâm Tổ chức & Cán bộ",
				subtitle: "Cơ cấu tổ chức, quyết định nhân sự và báo cáo lao động tại một nơi.",
			},
			panels: {
				"Cấu trúc": {
					eyebrow: "Quyết định đã ký",
					desc: "Toàn bộ quyết định về bổ nhiệm, điều động và khen thưởng cán bộ.",
					layout: "split",
					cols: 1,
				},
				"Nhập liệu": {
					eyebrow: "Danh mục nền tảng",
					desc: "Khai báo và chuẩn hóa dữ liệu gốc về đơn vị, chức danh, định biên.",
					layout: "split",
					cols: 1,
				},
				"Báo cáo quy mô - định biên lao động": {
					eyebrow: "Theo dõi & đối soát",
					title: "Quy mô - định biên",
					desc: "Bức tranh quy mô lao động so với định biên được duyệt.",
					layout: "stack",
					cols: 1,
				},
				"Báo cáo cơ cấu lao động": {
					eyebrow: "Theo dõi & đối soát",
					title: "Cơ cấu lao động",
					desc: "Phân tích lao động theo tuổi, chức danh, vị trí và phòng ban.",
					layout: "stack",
					cols: 1,
				},
				"Báo cáo biến động nhân sự - tổ chức": {
					eyebrow: "Theo dõi & đối soát",
					title: "Biến động nhân sự",
					desc: "Tăng giảm lao động, bổ nhiệm và cán bộ đến tuổi nghỉ hưu.",
					layout: "split",
					cols: 2,
				},
			},
			/* Bố cục hàng. Panel không khai báo ở đây sẽ tự xuống cuối, full width. */
			rows: [
				["Cấu trúc", "Nhập liệu"],
				["Báo cáo quy mô - định biên lao động", "Báo cáo cơ cấu lao động"],
				["Báo cáo biến động nhân sự - tổ chức"],
			],
		},

		"1.2 Công": {
			hero: {
				icon: "calendar-check",
				title: "Trung tâm Ca/Kíp & Chấm công",
				subtitle:
					"Thiết lập ca, phân/chuyển kíp, tạo ca kế hoạch và đối chiếu bảng công tại một nơi.",
			},
			items: {
				"Kíp làm việc": {
					i: "users-round",
					s: "Khai báo lịch tuần của từng kíp",
				},
				"Loại ca làm việc": {
					i: "calendar",
					s: "Khai báo giờ vào, giờ ra của ca",
				},
				"Danh sách ngày nghỉ": {
					i: "calendar-check",
					s: "Ngày nghỉ dùng khi sinh ca kế hoạch",
				},
				"Phân / chuyển kíp hàng loạt": {
					i: "shuffle",
					s: "Chọn nhiều nhân sự để phân hoặc đổi kíp",
				},
				"Lịch sử phân kíp": {
					i: "share-2",
					s: "Khoảng thời gian nhân sự thuộc từng kíp",
				},
				"Ca kế hoạch": {
					i: "clipboard-list",
					s: "Ca làm cụ thể của nhân sự theo ngày",
				},
				"Dữ liệu máy chấm công": {
					i: "contact-card",
					s: "Các lượt vào/ra nhận từ máy chấm công",
				},
				"Xác nhận chấm công bất thường": {
					i: "shield-alert",
					s: "Xử lý ngày công cần giải trình hoặc phê duyệt",
				},
				"Bảng công ngày": {
					i: "calendar-check",
					s: "Đối chiếu ca, giờ vào/ra và trạng thái từng ngày",
				},
				"Chi tiết chấm công không theo ca": {
					i: "clipboard-list",
					s: "Chi tiết các lượt vào/ra và số giờ theo ngày",
				},
				"Tổng hợp chấm công tháng": {
					i: "file-chart",
					s: "Bảng ký hiệu công theo từng nhân sự trong tháng",
				},
				"Báo cáo công hàng tháng": {
					t: "Báo cáo Công hàng tháng",
					i: "chart-column",
				},
				"Báo cáo tăng ca hàng tháng": {
					t: "Báo cáo Tăng ca hàng tháng",
					i: "chart-column",
				},
				"Kết quả chấm công": {
					i: "circle-check-big",
					s: "Các bản ghi Attendance đã được tạo",
				},
			},
			panels: {
				"Thiết lập ca/kíp": {
					eyebrow: "Danh mục nền tảng",
					desc: "Khai báo loại ca, lịch tuần của kíp và ngày nghỉ áp dụng.",
					layout: "split",
					cols: 2,
				},
				"Phân và chuyển kíp": {
					eyebrow: "Vận hành ca/kíp",
					desc: "Phân/chuyển kíp hàng loạt, quản lý lịch sử và ca kế hoạch theo ngày.",
					layout: "split",
					cols: 2,
				},
				"Bảng công & đối chiếu": {
					eyebrow: "Dữ liệu chấm công",
					desc: "Kiểm tra dữ liệu máy chấm công, xác nhận bất thường và tổng hợp ngày/tháng.",
					layout: "split",
					cols: 2,
				},
			},
			rows: [["Thiết lập ca/kíp"], ["Phân và chuyển kíp"], ["Bảng công & đối chiếu"]],
		},

		"1.3 Hồ sơ": {
			hero: {
				icon: "id-card",
				title: "Trung tâm Hồ sơ Nhân sự",
				subtitle: "Quản lý hồ sơ, quan hệ lao động và tra cứu báo cáo tại một nơi.",
			},
			/* Workspace này còn chart + custom block; hub chỉ vẽ phần lối tắt/báo cáo,
			   các block kia vẫn còn nguyên trong dữ liệu và hiện lại khi bấm Edit. */
			skip_blocks: ["chart", "custom_block", "number_card", "quick_list"],

			/* Nhãn item -> { t: tiêu đề hiển thị, i: icon, s: dòng phụ } — chỉ áp dụng cho workspace này */
			items: {
				"Danh sách nhân sự": { i: "users-round", s: "Nhân sự đang làm việc" },
				"Danh bạ nội bộ": { i: "contact-card" },
				"Sổ lao động": { i: "book-open" },
				"Sơ yếu lý lịch 2C-TW": { t: "Sơ yếu lý lịch 2C TW", i: "contact-card" },
				"Danh sách nhân thân": { i: "users" },
				"Danh sách sinh nhật": { i: "cake" },
				"Danh sách sinh nhật (trong tháng)": { t: "Danh sách sinh nhật", i: "cake" },
				"Danh sách nhân sự công tác (theo tuần)": {
					t: "Nhân sự công tác theo tuần",
					i: "building",
				},
				"Danh sách cán bộ sắp nghỉ hưu": { t: "Cán bộ sắp nghỉ hưu", i: "calendar" },
				"Tình hình sử dụng lao động": {
					i: "chart-column",
					route: "/app/query-report/BÁO CÁO TÌNH HÌNH SỬ DỤNG LAO ĐỘNG",
				},

				"Hợp đồng lao động": { i: "file-text", s: "Danh mục loại hợp đồng" },
				"Báo cáo HĐLĐ các loại": { t: "Báo cáo HĐLĐ các loại", i: "file-chart" },
				"Quá trình HĐLĐ": { i: "share-2" },
				"Danh sách HĐLĐ hiện tại": { i: "circle-check-big" },
				"Danh sách chấm dứt HĐLĐ": { i: "file-x" },
				"Danh sách Cán bộ hết hạn HĐLĐ": {
					t: "Cán bộ hết hạn HĐLĐ",
					i: "triangle-alert",
				},

				"Danh sách khen thưởng": { i: "award" },
				"Danh sách CBNV bị kỷ luật lao động": {
					t: "CBNV bị kỷ luật lao động",
					i: "shield-alert",
				},

				"LĐ cấp cao / LĐ cấp trung": { i: "user-levels" },
				"Danh sách cán bộ quy hoạch": { i: "clipboard-list" },
				"Danh sách Cán bộ đến hạn Bổ nhiệm lại": {
					t: "Cán bộ đến hạn bổ nhiệm lại",
					i: "refresh-cw",
				},
				"Danh sách cán bộ nghỉ hưu": { i: "user-round-plus" },
				"Danh sách cán bộ dự kiến nghỉ hưu": {
					t: "Cán bộ dự kiến nghỉ hưu",
					i: "calendar",
				},
			},

			/* Gộp cả panel vào panel khác (theo tiêu đề header / tên card) */
			regroup: {
				"Cấu trúc": "Hồ sơ cá nhân",
				"Nhập liệu": "Hồ sơ cá nhân",
			},
			/* Chuyển riêng từng item sang panel khác (theo nhãn gốc) */
			move: {
				"Hợp đồng lao động": "Quan hệ lao động",
			},

			panels: {
				"Hồ sơ cá nhân": {
					eyebrow: "Thông tin nền tảng",
					aside: 310,
					desc: "Quản lý danh sách nhân sự và tra cứu thông tin hồ sơ trọng yếu.",
					layout: "split",
					cols: 2,
					order: [
						"Danh sách nhân sự",
						"Danh bạ nội bộ",
						"Sổ lao động",
						"Sơ yếu lý lịch 2C TW",
						"Danh sách nhân thân",
						"Danh sách sinh nhật",
						"Nhân sự công tác theo tuần",
						"Cán bộ sắp nghỉ hưu",
						"Tình hình sử dụng lao động",
					],
				},
				"Quan hệ lao động": {
					eyebrow: "Theo dõi hợp đồng",
					aside: 310,
					desc: "Tra cứu loại hợp đồng, quá trình ký kết và các mốc hiệu lực.",
					layout: "split",
					cols: 2,
					order: [
						"Hợp đồng lao động",
						"Báo cáo HĐLĐ các loại",
						"Quá trình HĐLĐ",
						"Danh sách HĐLĐ hiện tại",
						"Danh sách chấm dứt HĐLĐ",
						"Cán bộ hết hạn HĐLĐ",
					],
				},
				"Khen thưởng kỷ luật": {
					eyebrow: "Ghi nhận & tuân thủ",
					aside: 310,
					title: "Khen thưởng – Kỷ luật",
					desc: "Tổng hợp thông tin ghi nhận thành tích và kỷ luật lao động.",
					layout: "split",
					cols: 2,
					order: ["Danh sách khen thưởng", "CBNV bị kỷ luật lao động"],
				},
				"Quy hoạch cán bộ": {
					eyebrow: "Nguồn cán bộ",
					desc: "Theo dõi đội ngũ lãnh đạo, quy hoạch, bổ nhiệm lại và nghỉ hưu.",
					layout: "split",
					cols: 2,
					/* cột mô tả hẹp hơn các panel khác -> tiêu đề xuống 2 dòng như thiết kế */
					aside: 190,
					order: [
						"LĐ cấp cao / LĐ cấp trung",
						"Danh sách cán bộ quy hoạch",
						"Cán bộ đến hạn bổ nhiệm lại",
						"Danh sách cán bộ nghỉ hưu",
						"Cán bộ dự kiến nghỉ hưu",
					],
				},
			},
			/* Mỗi panel chiếm trọn bề ngang và xếp dọc -> bố cục giữ nguyên tỉ lệ
			   ở mọi bề rộng, không đổi hình khi màn hình to lên.
			   (Ô lồng mảng = một cột chứa nhiều panel xếp chồng, xem "1.1 Tổ chức".) */
			rows: [
				["Hồ sơ cá nhân"],
				["Quan hệ lao động"],
				["Khen thưởng kỷ luật"],
				["Quy hoạch cán bộ"],
			],
		},
	};

	const BAR_COLORS = ["#1f3a68", "#2f5ea8", "#4a86d8", "#88b3ea", "#c2d8f4"];
	const SOON_TOKEN = "đang phát triển";

	/* ======================================================================
	 * 3. TIỆN ÍCH
	 * ==================================================================== */
	const esc = (s) =>
		String(s == null ? "" : s)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");

	const strip_tags = (html) => {
		const d = document.createElement("div");
		d.innerHTML = html || "";
		return (d.textContent || "").trim();
	};

	const t = (s) => (window.frappe && frappe._ ? frappe._(s) : s);

	const norm = (s) => {
		const v = String(s == null ? "" : s);
		return window.frappe && frappe.utils && frappe.utils.unescape_html
			? frappe.utils.unescape_html(v)
			: v;
	};

	const is_soon = (item) =>
		String(item && item.link_to ? item.link_to : "")
			.trim()
			.toLowerCase() === SOON_TOKEN;

	/** Meta của item: ưu tiên khai báo riêng của workspace, rồi tới bảng dùng chung. */
	const item_meta = (label, cfg) =>
		(cfg && cfg.items && cfg.items[label]) || ITEM_META[label] || null;

	const display_title = (label, cfg) => {
		const meta = item_meta(label, cfg);
		if (meta && meta.t) return meta.t;
		return String(label || "").replace(/^\s*Báo cáo\s+/i, "");
	};

	const display_sub = (label, cfg) => {
		const meta = item_meta(label, cfg);
		return (meta && meta.s) || "Mở màn hình";
	};

	const pick_icon = (label, cfg) => {
		const meta = item_meta(label, cfg);
		if (meta && meta.i) return meta.i;
		for (const [re, name] of ICON_RULES) {
			if (re.test(label || "")) return name;
		}
		return "layout-grid";
	};

	const key_of = (s) => norm(String(s == null ? "" : s)).trim().toLowerCase();

	/** Duyệt cấu hình rows (có thể lồng mảng) ra danh sách khoá panel phẳng. */
	const flatten_rows = (rows) => {
		const out = [];
		(rows || []).forEach((row) =>
			(row || []).forEach((cell) => {
				if (Array.isArray(cell)) cell.forEach((k) => out.push(k));
				else out.push(cell);
			})
		);
		return out;
	};

	/** Dựng href giống hệt widget gốc của Frappe để điều hướng không đổi hành vi. */
	const build_href = (item, cfg) => {
		if (!window.frappe || !frappe.utils || !frappe.utils.generate_route) return "";
		try {
			const meta = item_meta(item.label || item.name || "", cfg);
			if (meta && meta.route) return meta.route;
			if (item.type === "URL") return item.url || "";

			const opts = {
				name: item.link_to,
				type: item.link_type || item.type,
				doctype: item.doctype || item.ref_doctype,
				is_query_report: item.is_query_report,
				doc_view: item.doc_view,
				kanban_board: item.kanban_board,
				report_ref_doctype: item.report_ref_doctype,
				route: item.route,
			};
			// giống links_widget.js: report builder lấy doctype từ dependencies
			if (String(opts.type || "").toLowerCase() === "report" && !item.is_query_report) {
				opts.doctype = item.doctype || item.dependencies || item.ref_doctype;
			}

			let href = frappe.utils.generate_route(opts);

			// bộ lọc của shortcut -> query string, router sẽ nạp vào route_options
			if (item.stats_filter && String(item.type).toLowerCase() === "doctype") {
				const filters = frappe.utils.get_filter_from_json(item.stats_filter);
				const qs = [];
				for (const key in filters || {}) {
					const v = filters[key];
					qs.push(
						encodeURIComponent(key) +
							"=" +
							encodeURIComponent(typeof v === "object" ? JSON.stringify(v) : v)
					);
				}
				if (qs.length) href += (href.indexOf("?") === -1 ? "?" : "&") + qs.join("&");
			}
			return href;
		} catch (e) {
			return "";
		}
	};

	/* ======================================================================
	 * 4. ĐỌC DỮ LIỆU WORKSPACE -> DANH SÁCH PANEL
	 * ==================================================================== */
	const find_widget = (page_data, bucket, name) => {
		const items = (page_data && page_data[bucket] && page_data[bucket].items) || [];
		const want = norm(t(name));
		return items.find((o) => norm(o.label) === want);
	};

	function collect_panels(content, page_data) {
		const panels = [];
		let current = null;

		const push_current = () => {
			if (current && current.items.length) panels.push(current);
			current = null;
		};

		(content || []).forEach((block) => {
			const type = block && block.type;
			const data = (block && block.data) || {};

			if (type === "header") {
				push_current();
				current = { key: strip_tags(data.text), items: [] };
				return;
			}

			if (type === "shortcut") {
				const w = find_widget(page_data, "shortcuts", data.shortcut_name);
				if (!w) return;
				if (!current) current = { key: "", items: [] };
				current.items.push(w);
				return;
			}

			if (type === "card") {
				push_current();
				const w = find_widget(page_data, "cards", data.card_name);
				if (!w || w.hidden) return;
				panels.push({
					key: data.card_name,
					desc_from_card: w.description,
					items: (w.links || []).filter((l) => !l.hidden),
				});
				return;
			}

			if (type === "spacer" || type === "paragraph") return;
			// các block khác (chart, number_card, custom_block...) giữ nguyên editor gốc
			// => xem is_supported() bên dưới
		});

		push_current();
		return panels;
	}

	/**
	 * Chỉ nhận vẽ lại khi workspace chỉ gồm các block mà hub hiểu được.
	 * Có block lạ (chart, custom html, quick list...) -> trả về editor gốc để
	 * tuyệt đối không mất nội dung, trừ khi workspace khai báo skip_blocks.
	 */
	const SUPPORTED_BLOCKS = ["header", "shortcut", "card", "spacer", "paragraph"];
	const is_supported = (content, cfg) => {
		const skip = (cfg && cfg.skip_blocks) || [];
		return (
			Array.isArray(content) &&
			content.length > 0 &&
			content.every(
				(b) =>
					SUPPORTED_BLOCKS.indexOf(b && b.type) !== -1 ||
					skip.indexOf(b && b.type) !== -1
			)
		);
	};

	/**
	 * Gộp panel (regroup), chuyển item lẻ sang panel khác (move), bỏ trùng và
	 * sắp xếp theo cấu hình. Không có cấu hình -> giữ nguyên như đọc từ workspace.
	 */
	function apply_layout(panels, cfg) {
		const regroup = cfg.regroup || {};
		const move = cfg.move || {};
		const has_rules = Object.keys(regroup).length || Object.keys(move).length;

		let list = panels;

		if (has_rules) {
			const index = new Map();
			const out = [];
			const ensure = (key, src) => {
				if (!index.has(key)) {
					const p = { key: key, desc_from_card: "", items: [] };
					index.set(key, p);
					out.push(p);
				}
				const p = index.get(key);
				if (!p.desc_from_card && src && src.desc_from_card) {
					p.desc_from_card = src.desc_from_card;
				}
				return p;
			};

			// tạo trước theo thứ tự khai báo để việc gộp không phụ thuộc vị trí block
			flatten_rows(cfg.rows).forEach((k) => ensure(k, null));

			panels.forEach((panel) => {
				const fallback = Object.prototype.hasOwnProperty.call(regroup, panel.key)
					? regroup[panel.key]
					: panel.key;
				panel.items.forEach((item) => {
					const target = move[norm(item.label)] || fallback;
					if (!target) return;
					ensure(target, panel).items.push(item);
				});
			});

			list = out;
		}

		list.forEach((panel) => {
			const pc = (cfg.panels && cfg.panels[panel.key]) || {};

			// bỏ trùng: cùng một tiêu đề hiển thị chỉ giữ lần xuất hiện đầu
			const seen = new Set();
			let items = panel.items.filter((it) => {
				const k = key_of(display_title(norm(it.label), cfg));
				if (seen.has(k)) return false;
				seen.add(k);
				return true;
			});

			if (pc.order && pc.order.length) {
				const rank = new Map(pc.order.map((v, i) => [key_of(v), i]));
				items = items
					.map((it, i) => {
						const r = rank.get(key_of(display_title(norm(it.label), cfg)));
						return [it, r == null ? pc.order.length + i : r];
					})
					.sort((a, b) => a[1] - b[1])
					.map((pair) => pair[0]);
			}

			panel.items = items;
		});

		return list.filter((p) => p.items.length);
	}

	/* ======================================================================
	 * 5. RENDER
	 * ==================================================================== */
	function render_item(item, index, cfg) {
		const label = item.label || item.name || "";
		const title = display_title(label, cfg);
		const soon = is_soon(item);
		const blocked = soon || (item.dependencies && item.incomplete_dependencies);
		const href = blocked ? "" : build_href(item, cfg);
		const external = !blocked && item.type === "URL";

		const attrs = [
			'class="vnt-item' + (soon ? " is-soon" : "") + '"',
			'data-vnt-index="' + index + '"',
			'title="' + esc(label) + '"',
		];
		if (href) attrs.push('href="' + esc(href) + '"');
		if (external) attrs.push('target="_blank" rel="noopener"');
		if (blocked) attrs.push('role="button" tabindex="0"');

		return (
			"<a " +
			attrs.join(" ") +
			">" +
			'<span class="vnt-item__icon">' +
			icon(pick_icon(label, cfg)) +
			"</span>" +
			'<span class="vnt-item__body">' +
			'<span class="vnt-item__title">' +
			esc(title) +
			"</span>" +
			'<span class="vnt-item__sub">' +
			esc(soon ? "Đang phát triển" : display_sub(label, cfg)) +
			"</span>" +
			"</span>" +
			'<span class="vnt-item__arrow">' +
			icon("arrow-right") +
			"</span>" +
			(soon ? '<span class="vnt-item__badge">Sắp ra mắt</span>' : "") +
			"</a>"
		);
	}

	function render_panel(panel, cfg, counter) {
		const pc = (cfg.panels && cfg.panels[panel.key]) || {};
		const layout = pc.layout === "stack" ? "stack" : "split";
		const cols = pc.cols || 1;
		const title = pc.title || panel.key;
		const desc = pc.desc || panel.desc_from_card || "";

		const items = panel.items
			.map((it) => {
				// giữ đúng thứ tự vẽ để data-vnt-index tra ngược lại được item gốc
				counter.items.push(it);
				return render_item(it, counter.n++, cfg);
			})
			.join("");

		return (
			'<section class="vnt-panel vnt-panel--' +
			layout +
			'"' +
			(pc.aside ? ' style="--vnt-aside:' + Number(pc.aside) + 'px"' : "") +
			">" +
			'<div class="vnt-panel__aside">' +
			(pc.eyebrow ? '<div class="vnt-eyebrow">' + esc(pc.eyebrow) + "</div>" : "") +
			'<h2 class="vnt-panel__title">' +
			esc(title) +
			"</h2>" +
			(desc ? '<p class="vnt-panel__desc">' + esc(desc) + "</p>" : "") +
			"</div>" +
			'<div class="vnt-panel__items" style="--vnt-cols:' +
			cols +
			'">' +
			items +
			"</div>" +
			"</section>"
		);
	}

	function render_rows(panels, cfg) {
		const by_key = new Map(panels.map((p) => [p.key, p]));
		const used = new Set();
		const counter = { n: 0, items: [] };
		const rows = [];

		(cfg.rows || []).forEach((row) => {
			// mỗi ô là một panel, hoặc một mảng panel xếp chồng trong cùng một cột
			const cells = (row || [])
				.map((cell) =>
					Array.isArray(cell)
						? cell.filter((k) => by_key.has(k))
						: by_key.has(cell)
						? [cell]
						: []
				)
				.filter((cell) => cell.length);
			if (!cells.length) return;

			cells.forEach((cell) => cell.forEach((k) => used.add(k)));

			const html = cells
				.map((cell) =>
					cell.length === 1
						? render_panel(by_key.get(cell[0]), cfg, counter)
						: '<div class="vnt-col">' +
						  cell.map((k) => render_panel(by_key.get(k), cfg, counter)).join("") +
						  "</div>"
				)
				.join("");

			rows.push(
				'<div class="vnt-row vnt-row--' + Math.min(cells.length, 2) + '">' + html + "</div>"
			);
		});

		// panel chưa được xếp hàng -> đưa xuống cuối, full width
		panels
			.filter((p) => !used.has(p.key))
			.forEach((p) => {
				rows.push(
					'<div class="vnt-row vnt-row--1">' + render_panel(p, cfg, counter) + "</div>"
				);
			});

		return {
			html: '<div class="vnt-rows">' + rows.join("") + "</div>",
			total: counter.n,
			items: counter.items,
		};
	}

	function render_hub(cfg, panels, sink) {
		const body = render_rows(panels, cfg);
		if (sink) body.items.forEach((it) => sink.push(it));

		const hero =
			'<section class="vnt-hero">' +
			'<div class="vnt-hero__deco"></div>' +
			'<div class="vnt-hero__icon">' +
			icon(cfg.hero.icon) +
			"</div>" +
			'<div class="vnt-hero__text">' +
			'<h1 class="vnt-hero__title">' +
			esc(cfg.hero.title) +
			"</h1>" +
			'<p class="vnt-hero__sub">' +
			esc(cfg.hero.subtitle) +
			"</p>" +
			"</div>" +
			'<div class="vnt-hero__badge">' +
			body.total +
			" tiện ích</div>" +
			"</section>";

		const stat = cfg.stat
			? '<section class="vnt-stat is-loading" data-vnt-stat>' +
			  '<div class="vnt-stat__head"><div>' +
			  '<div class="vnt-eyebrow">' +
			  esc(cfg.stat.eyebrow) +
			  "</div>" +
			  '<h2 class="vnt-stat__title">' +
			  esc(cfg.stat.title) +
			  "</h2></div>" +
			  (cfg.stat.action
					? '<button type="button" class="vnt-btn-ghost" data-vnt-stat-action>' +
					  esc(cfg.stat.action.label) +
					  "</button>"
					: "") +
			  "</div>" +
			  '<div class="vnt-stat__skeleton"></div>' +
			  '<div class="vnt-stat__body"></div>' +
			  "</section>"
			: "";

		return '<div class="vnt-hub">' + hero + stat + body.html + "</div>";
	}

	/* ======================================================================
	 * 6. KHỐI SỐ LIỆU (nạp sau, có chỗ giữ sẵn nên không xô lệch layout)
	 * ==================================================================== */
	async function fill_stat($hub, cfg) {
		const el = $hub.querySelector("[data-vnt-stat]");
		if (!el || !cfg.stat) return;

		let rows = [];
		try {
			rows = await frappe.xcall("frappe.client.get_list", {
				doctype: cfg.stat.doctype,
				fields: ["name", cfg.stat.field],
				limit_page_length: 0,
			});
		} catch (e) {
			el.remove(); // không đọc được (thiếu quyền / thiếu field) -> ẩn hẳn, không báo lỗi
			return;
		}
		if (!Array.isArray(rows)) rows = [];

		const buckets = new Map();
		rows.forEach((r) => {
			const k = (r[cfg.stat.field] || "").trim() || "Chưa phân loại";
			buckets.set(k, (buckets.get(k) || 0) + 1);
		});

		const total = rows.length;
		const groups = [...buckets.entries()].sort((a, b) => b[1] - a[1]);

		const bar = groups
			.map(
				([, c], i) =>
					'<span style="width:' +
					(total ? (c / total) * 100 : 0) +
					"%;background:" +
					BAR_COLORS[i % BAR_COLORS.length] +
					'"></span>'
			)
			.join("");

		const legend = groups
			.map(
				([k, c], i) =>
					"<li><i style=\"background:" +
					BAR_COLORS[i % BAR_COLORS.length] +
					'"></i>' +
					'<span class="vnt-legend__k">' +
					esc(k) +
					"</span>" +
					'<span class="vnt-legend__v">' +
					c +
					"&nbsp;&nbsp;" +
					(total ? Math.round((c / total) * 100) : 0) +
					"%</span></li>"
			)
			.join("");

		el.querySelector(".vnt-stat__body").innerHTML =
			'<div class="vnt-stat__figure">' +
			'<div class="vnt-stat__num">' +
			total +
			"</div>" +
			'<div class="vnt-stat__unit">' +
			esc(cfg.stat.unit) +
			"</div>" +
			'<div class="vnt-stat__note">' +
			groups.length +
			" " +
			esc(cfg.stat.group_unit) +
			"</div>" +
			"</div>" +
			'<div class="vnt-stat__chart">' +
			'<div class="vnt-bar">' +
			bar +
			"</div>" +
			'<ul class="vnt-legend">' +
			legend +
			"</ul>" +
			"</div>";

		el.classList.remove("is-loading");
	}

	/* ======================================================================
	 * 7. GẮN / GỠ HUB
	 * ==================================================================== */
	const HUB_SELECTOR = ".vnt-hub";

	function unmount(body_el) {
		if (!body_el) return;
		const old = body_el.querySelector(":scope > " + HUB_SELECTOR);
		if (old) old.remove();
		body_el.classList.remove("vnt-hub-on");
	}

	function mount(ws) {
		const body_el = ws && ws.body && ws.body[0];
		if (!body_el) return;

		unmount(body_el);

		if (body_el.classList.contains("edit-mode")) return;

		const page = ws._page;
		const title = page && page.title;
		const cfg = title && HUB_CONFIG[title];
		if (!cfg) return;
		if (!is_supported(ws.content, cfg)) return;

		const panels = apply_layout(collect_panels(ws.content, ws.page_data), cfg);
		if (!panels.length) return;

		// tra cứu nhanh item khi click, không cần đọc lại DOM (đúng thứ tự đã vẽ)
		const ordered = [];
		const container = document.createElement("div");
		container.innerHTML = render_hub(cfg, panels, ordered);
		const hub = container.firstElementChild;
		if (!hub) return;

		hub.__vnt_items = ordered;
		hub.__vnt_cfg = cfg;

		body_el.classList.add("vnt-hub-on");
		body_el.insertBefore(hub, body_el.firstChild);

		fill_stat(hub, cfg);
	}

	/* ======================================================================
	 * 8. SỰ KIỆN (uỷ quyền 1 listener duy nhất cho cả trang)
	 * ==================================================================== */
	document.addEventListener(
		"click",
		(e) => {
			const hub = e.target.closest ? e.target.closest(HUB_SELECTOR) : null;
			if (!hub) return;

			const action = e.target.closest("[data-vnt-stat-action]");
			if (action) {
				const route = hub.__vnt_cfg && hub.__vnt_cfg.stat && hub.__vnt_cfg.stat.action;
				if (route && route.route) frappe.set_route(route.route);
				return;
			}

			const node = e.target.closest(".vnt-item");
			if (!node) return;

			if (node.classList.contains("is-soon")) {
				e.preventDefault();
				frappe.show_alert(
					{ message: "Tính năng đang được phát triển.", indicator: "orange" },
					4
				);
				return;
			}

			const item = (hub.__vnt_items || [])[Number(node.dataset.vntIndex)];
			if (item && item.dependencies && item.incomplete_dependencies) {
				e.preventDefault();
				frappe.show_alert(
					{
						message:
							"Cần tạo dữ liệu trước: " +
							[].concat(item.incomplete_dependencies).join(", "),
						indicator: "orange",
					},
					5
				);
			}
			// còn lại: để href + router của Frappe xử lý (giữ nguyên ctrl/cmd + click)
		},
		true
	);

	// Enter/Space cho item không có href
	document.addEventListener("keydown", (e) => {
		if (e.key !== "Enter" && e.key !== " ") return;
		const node = e.target.closest && e.target.closest(".vnt-item[role='button']");
		if (!node) return;
		e.preventDefault();
		node.click();
	});

	/* ======================================================================
	 * 9. HOOK VÀO WORKSPACE CỦA FRAPPE
	 * ==================================================================== */
	function patch() {
		const klass = window.frappe && frappe.views && frappe.views.Workspace;
		if (!klass || klass.prototype.__vnt_hub_patched) return false;

		const proto = klass.prototype;
		proto.__vnt_hub_patched = true;

		const orig_show_page = proto.show_page;
		proto.show_page = async function (page) {
			const out = await orig_show_page.call(this, page);
			try {
				mount(this);
				watch_edit_mode(this);
			} catch (err) {
				console.error("[vnt-workspace-hub]", err);
			}
			return out;
		};

		return true;
	}

	/** Vào Edit -> gỡ hub, trả editor gốc. Thoát Edit -> vẽ lại. */
	function watch_edit_mode(ws) {
		const body_el = ws && ws.body && ws.body[0];
		if (!body_el || body_el.__vnt_edit_observer) return;

		let was_edit = body_el.classList.contains("edit-mode");
		const obs = new MutationObserver(() => {
			const now_edit = body_el.classList.contains("edit-mode");
			if (now_edit === was_edit) return;
			was_edit = now_edit;
			if (now_edit) {
				unmount(body_el);
			} else {
				// chờ editor/ dữ liệu ổn định rồi mới vẽ lại
				setTimeout(() => {
					try {
						mount(ws);
					} catch (err) {
						console.error("[vnt-workspace-hub]", err);
					}
				}, 60);
			}
		});
		obs.observe(body_el, { attributes: true, attributeFilter: ["class"] });
		body_el.__vnt_edit_observer = obs;
	}

	if (!patch()) {
		// bundle desk chưa nạp xong -> thử lại vài nhịp rồi thôi
		let tries = 0;
		const timer = setInterval(() => {
			if (patch() || ++tries > 50) clearInterval(timer);
		}, 100);
	}
})();

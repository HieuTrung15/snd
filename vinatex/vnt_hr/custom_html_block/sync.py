"""Đồng bộ các Custom HTML Block của VNT HR từ file nguồn trong app vào DB.

Vì "Custom HTML Block" là doctype thường (bản ghi chỉ nằm trong DB, không được
Frappe tự export ra app), ta giữ nội dung dưới dạng file html/css/js trong app để
review được bằng git, rồi upsert vào DB bằng hàm ở đây.

Chạy lại bất cứ lúc nào sau khi sửa file nguồn:

    bench --site <site> execute vinatex.vnt_hr.custom_html_block.sync.sync_all
"""

import os

import frappe

DOCTYPE = "Custom HTML Block"

# tên bản ghi -> thư mục chứa <slug>.html / .css / .js
BLOCKS = {
	"Bảng tin chỉ đạo điều hành": "leadership_board",
	"Trang chủ tổng hợp": "home_dashboard",
}


def _read(folder: str, ext: str) -> str:
	path = os.path.join(os.path.dirname(__file__), folder, f"{folder}.{ext}")
	if not os.path.exists(path):
		return ""
	with open(path, encoding="utf-8") as f:
		return f.read()


def sync_block(name: str, folder: str) -> str:
	"""Tạo mới hoặc cập nhật một Custom HTML Block. Idempotent."""
	values = {
		"html": _read(folder, "html"),
		"style": _read(folder, "css"),
		"script": _read(folder, "js"),
		"private": 0,
	}

	if frappe.db.exists(DOCTYPE, name):
		doc = frappe.get_doc(DOCTYPE, name)
		changed = [k for k, v in values.items() if (doc.get(k) or "") != (v or "")]
		if not changed:
			return "unchanged"
		doc.update(values)
		doc.save(ignore_permissions=True)
		return "updated: " + ", ".join(changed)

	# autoname của doctype này là "prompt" -> name truyền vào được giữ nguyên
	doc = frappe.get_doc({"doctype": DOCTYPE, "name": name, **values})
	doc.insert(ignore_permissions=True)
	return "created"


def sync_all():
	for name, folder in BLOCKS.items():
		result = sync_block(name, folder)
		print(f"{DOCTYPE} '{name}': {result}")
	frappe.db.commit()

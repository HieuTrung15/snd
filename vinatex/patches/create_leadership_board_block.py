"""Tạo Custom HTML Block "Bảng tin chỉ đạo điều hành" từ file nguồn trong app.

Workspace cùng tên dùng block này thay cho việc redirect ra /leadership-spa.
"""

from vinatex.vnt_hr.custom_html_block.sync import sync_all


def execute():
	sync_all()

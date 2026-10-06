# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

"""Xuất HĐLĐ của Employee ra file Word (.docx).

Nội dung được render bằng CHÍNH print format tương ứng (cùng template Jinja, cùng dữ liệu
như khi bấm In), sau đó chuyển HTML -> WordprocessingML. Bố cục trang (khổ A4, lề) và độ rộng
các bảng lấy theo các file Word mẫu gốc mà print format đã được dựng lại từ đó.
"""

import io
import re
import unicodedata
import zipfile
from urllib.parse import quote
from xml.sax.saxutils import escape

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.www.printview import get_html_and_style
from lxml import html as lxml_html
from werkzeug.wrappers import Response

DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Lề trang (twips) theo file Word mẫu
MARGINS_A = {"top": 907, "right": 1021, "bottom": 907, "left": 1531}  # 6 tháng, 36 tháng, KXĐ
MARGINS_B = {"top": 1134, "right": 1134, "bottom": 1134, "left": 1701}  # khoán việc, thử việc

# Loại HĐ -> print format + bố cục (độ rộng cột bảng tính bằng twips, lấy từ file Word mẫu)
CONTRACTS = {
	"6_thang": {
		"label": "HĐLĐ 6 tháng",
		"print_format": "HĐLĐ xác định thời hạn 6 tháng",
		"margins": MARGINS_A,
		"grids": {"hdr": [5211, 270, 5259], "party": [2836, 289, 6231], "sign": [4440, 5131]},
	},
	"3_nam": {
		"label": "HĐLĐ 3 năm",
		"print_format": "HĐLĐ xác định thời hạn 36 tháng",
		"margins": MARGINS_A,
		"grids": {"hdr": [5211, 270, 5259], "party": [2836, 289, 6231], "sign": [4344, 5011]},
	},
	"khoan_viec": {
		"label": "HĐLĐ khoán việc",
		"print_format": "Hợp đồng khoán việc",
		"margins": MARGINS_B,
		"grids": {"hdr": [5218, 270, 5266], "party": [2968, 302, 6521], "sign": [4315, 4973]},
	},
	"thu_viec": {
		"label": "HĐLĐ thử việc",
		"print_format": "Hợp đồng thử việc",
		"margins": MARGINS_B,
		"grids": {"hdr": [5211, 270, 5259], "party": [2836, 289, 6231], "sign": [4315, 4973]},
	},
	"kxd": {
		"label": "HĐLĐ KXĐ thời hạn",
		"print_format": "HĐLĐ không xác định thời hạn",
		"margins": MARGINS_A,
		"grids": {"hdr": [5211, 270, 5259], "party": [2836, 289, 6231], "sign": [4440, 5131]},
	},
}

PAGE_W, PAGE_H = 11907, 16839  # A4
BASE_SZ = 26  # 13pt (half-points)
HDR_SZ = 24  # 12pt
TITLE_SZ = 32  # 16pt
PARTY_INDENT = -176  # tblInd của bảng thông tin các bên
SIGN_SPACE_H = 1587  # 2.8cm chỗ ký

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@frappe.whitelist()
def download_contract_docx(employee: str, contract_type: str):
	cfg = CONTRACTS.get(contract_type)
	if not cfg:
		frappe.throw(_("Loại hợp đồng không hợp lệ: {0}").format(contract_type))

	doc = frappe.get_doc("Employee", employee)
	doc.check_permission("print")

	if frappe.db.get_value("Print Format", cfg["print_format"], "disabled") in (None, 1):
		frappe.throw(_("Print Format {0} không tồn tại hoặc đã bị vô hiệu hoá.").format(cfg["print_format"]))

	html = get_html_and_style(doc="Employee", name=employee, print_format=cfg["print_format"], no_letterhead=True)["html"]
	content = build_docx(html, cfg, title=f"{cfg['label']} - {doc.employee_name or doc.name}")

	filename = f"{cfg['label']} - {doc.employee_name or ''} - {doc.name}.docx".replace("  ", " ")
	response = Response(content, mimetype=DOCX_MIMETYPE)
	response.headers["Content-Disposition"] = content_disposition(filename)
	return response


def content_disposition(filename: str) -> str:
	# RFC 6266: tên ASCII dự phòng + tên UTF-8 đầy đủ (giữ nguyên tiếng Việt)
	ascii_name = unicodedata.normalize("NFKD", filename.replace("Đ", "D").replace("đ", "d"))
	ascii_name = ascii_name.encode("ascii", "ignore").decode()
	ascii_name = re.sub(r'[^A-Za-z0-9._() -]+', "", ascii_name).strip() or "hop-dong.docx"
	return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


# ---------------------------------------------------------------------------
# HTML (print format) -> document.xml
# ---------------------------------------------------------------------------


def build_docx(html: str, cfg: dict, title: str = "") -> bytes:
	root = lxml_html.fromstring(html or "<div></div>")
	found = root.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " hdld ")]')
	if not found:
		frappe.throw(_("Không tìm thấy nội dung hợp đồng trong print format {0}.").format(cfg["print_format"]))

	converter = _Converter(cfg)
	body = converter.convert(found[0])

	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
		z.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
		z.writestr("_rels/.rels", ROOT_RELS_XML)
		z.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS_XML)
		z.writestr("word/document.xml", _document_xml(body, cfg))
		z.writestr("word/styles.xml", STYLES_XML)
		z.writestr("word/settings.xml", SETTINGS_XML)
		z.writestr("word/numbering.xml", NUMBERING_XML)
		z.writestr("docProps/core.xml", _core_xml(title))
		z.writestr("docProps/app.xml", APP_XML)
	return buf.getvalue()


def _classes(el) -> set:
	return set((el.get("class") or "").split())


def _style_font_size(el):
	m = re.search(r"font-size\s*:\s*([\d.]+)pt", el.get("style") or "")
	return int(round(float(m.group(1)) * 2)) if m else None


def _style_width_pct(el):
	m = re.search(r"width\s*:\s*([\d.]+)%", el.get("style") or "")
	return float(m.group(1)) if m else None


class _Converter:
	def __init__(self, cfg):
		self.cfg = cfg
		self.text_width = PAGE_W - cfg["margins"]["left"] - cfg["margins"]["right"]

	def convert(self, container) -> list[str]:
		out = []
		for el in container:
			if not isinstance(el.tag, str):
				continue  # comment
			if el.tag == "p":
				out.append(self.paragraph(el, _classes(el)))
			elif el.tag == "table":
				out.append(self.table(el))
			elif el.tag == "div":
				out.extend(self.convert(el))
		# Word yêu cầu phần thân không kết thúc bằng bảng: thêm 1 đoạn rỗng rất nhỏ
		if out and out[-1].startswith("<w:tbl>"):
			out.append(
				'<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/>'
				'<w:rPr><w:sz w:val="2"/><w:szCs w:val="2"/></w:rPr></w:pPr></w:p>'
			)
		return out

	# ---------- đoạn văn ----------

	def paragraph(self, el, classes, table_cls=None, first_col=False, keep_next=False):
		size = _style_font_size(el) or (TITLE_SZ if "title" in classes else HDR_SZ if table_cls == "hdr" else BASE_SZ)
		fmt = {
			"b": "b" in classes or "title" in classes,
			"i": "i" in classes,
			"u": "u" in classes,
			"sz": size,
		}
		segments = _collapse(_segments(el, fmt))

		num_prefix = None
		if "dash" in classes and segments:
			segments[0] = (re.sub(r"^[-–]\s*", "", segments[0][0]), segments[0][1])
		elif "num" in classes and segments:
			m = re.match(r"^(\d+\.)\s*(.*)$", segments[0][0], re.S)
			if m:
				num_prefix = m.group(1)
				segments[0] = (m.group(2), segments[0][1])

		if "c" in classes or "title" in classes or (table_cls == "sign"):
			jc = "center"
		elif "r" in classes:
			jc = "right"
		elif "l" in classes:
			jc = "left"
		else:
			jc = "both"

		before = 0
		if table_cls == "party":
			before = 40
		elif "num" in classes or ({"b", "u"} <= classes and not table_cls):
			before = 120  # "Điều ..." và mục 1./2./3.

		ppr = []
		if keep_next:
			ppr.append("<w:keepNext/>")
		if "dash" in classes:
			ppr.append('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
		ppr.append(f'<w:spacing w:before="{before}" w:after="0" w:line="276" w:lineRule="auto"/>')
		if "num" in classes:
			ppr.append('<w:ind w:left="284" w:hanging="284"/>')
		elif "ind" in classes:
			ppr.append('<w:ind w:firstLine="720"/>')
		elif table_cls == "party" and first_col:
			ppr.append('<w:ind w:firstLine="176"/>')
		ppr.append(f'<w:jc w:val="{jc}"/>')
		ppr.append(f"<w:rPr>{_rpr(fmt)}</w:rPr>")

		runs = []
		if num_prefix:
			runs.append(_run(num_prefix, fmt) + f"<w:r><w:rPr>{_rpr(fmt)}</w:rPr><w:tab/></w:r>")
		runs.extend(_run(text, f) for text, f in segments if text)
		return f"<w:p><w:pPr>{''.join(ppr)}</w:pPr>{''.join(runs)}</w:p>"

	# ---------- bảng ----------

	def table(self, el):
		tcls = _classes(el)
		kind = next((k for k in ("hdr", "party", "sign") if k in tcls), None)
		rows = [tr for tr in el.iter("tr")]
		ncols = max((sum(int(td.get("colspan") or 1) for td in tr.findall("td")) for tr in rows), default=1)

		grid = self.cfg["grids"].get(kind) if kind else None
		if not grid or len(grid) != ncols:
			grid = self._grid_from_html(rows, ncols)
		total = sum(grid)

		tblpr = [f'<w:tblW w:w="{total}" w:type="dxa"/>']
		if kind == "hdr":
			tblpr.append('<w:jc w:val="center"/>')
		elif kind == "party":
			tblpr.append(f'<w:tblInd w:w="{PARTY_INDENT}" w:type="dxa"/>')
		tblpr.append(
			"<w:tblBorders>"
			+ "".join(f'<w:{s} w:val="nil"/>' for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
			+ "</w:tblBorders>"
		)
		tblpr.append('<w:tblLayout w:type="fixed"/>')
		tblpr.append('<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="1" w:noVBand="1"/>')

		xml = ["<w:tbl>", f"<w:tblPr>{''.join(tblpr)}</w:tblPr>", "<w:tblGrid>"]
		xml += [f'<w:gridCol w:w="{w}"/>' for w in grid]
		xml.append("</w:tblGrid>")

		for r_idx, tr in enumerate(rows):
			tds = tr.findall("td")
			trpr = []
			if kind == "sign":
				trpr.append("<w:cantSplit/>")
			if kind == "sign" and all("space" in _classes(td) for td in tds):
				trpr.append(f'<w:trHeight w:val="{SIGN_SPACE_H}"/>')
			xml.append("<w:tr>" + (f"<w:trPr>{''.join(trpr)}</w:trPr>" if trpr else ""))
			col = 0
			for td in tds:
				span = int(td.get("colspan") or 1)
				width = sum(grid[col : col + span])
				tcpr = f'<w:tcW w:w="{width}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{span}"/>' if span > 1 else "")
				keep = kind == "sign" and r_idx < len(rows) - 1
				xml.append(f"<w:tc><w:tcPr>{tcpr}</w:tcPr>{self.cell(td, kind, col == 0, keep)}</w:tc>")
				col += span
			xml.append("</w:tr>")
		xml.append("</w:tbl>")
		return "".join(xml)

	def cell(self, td, kind, first_col, keep_next):
		td_cls = _classes(td) - {"lbl", "sep", "space"}
		paras = [p for p in td if isinstance(p.tag, str) and p.tag == "p"]
		if not paras:
			return self.paragraph(td, td_cls, table_cls=kind, first_col=first_col, keep_next=keep_next)
		return "".join(
			self.paragraph(p, td_cls | _classes(p), table_cls=kind, first_col=first_col, keep_next=keep_next)
			for p in paras
		)

	def _grid_from_html(self, rows, ncols):
		widths = [None] * ncols
		for tr in rows:
			col = 0
			for td in tr.findall("td"):
				span = int(td.get("colspan") or 1)
				pct = _style_width_pct(td)
				if span == 1 and pct and widths[col] is None:
					widths[col] = pct
				col += span
		known = sum(w for w in widths if w)
		missing = [i for i, w in enumerate(widths) if not w]
		for i in missing:
			widths[i] = max(100 - known, 0) / len(missing) if missing else 0
		return [int(round(self.text_width * (w or 0) / 100)) for w in widths]


# ---------- runs ----------


def _segments(el, fmt):
	"""Duyệt nội dung inline -> [(text, fmt)] (hỗ trợ b/strong/i/em/u/span/br)."""
	out = []
	if el.text:
		out.append((el.text, fmt))
	for child in el:
		if isinstance(child.tag, str):
			tag = child.tag.lower()
			if tag == "br":
				out.append(("\n", fmt))
			elif tag in ("p", "table", "div"):
				pass
			else:
				f = dict(fmt)
				cls = _classes(child)
				if tag in ("b", "strong") or "b" in cls:
					f["b"] = True
				if tag in ("i", "em") or "i" in cls:
					f["i"] = True
				if tag == "u" or "u" in cls:
					f["u"] = True
				f["sz"] = _style_font_size(child) or f["sz"]
				out.extend(_segments(child, f))
		if child.tail:
			out.append((child.tail, fmt))
	return out


def _collapse(segments):
	"""Gom khoảng trắng như trình duyệt hiển thị HTML."""
	res = []
	prev_space = True  # bỏ khoảng trắng đầu đoạn
	for text, f in segments:
		if text == "\n":
			res.append(("\n", f))
			prev_space = True
			continue
		t = re.sub(r"\s+", " ", INVALID_XML_CHARS.sub("", text.replace("\xa0", " ")))
		if prev_space:
			t = t.lstrip(" ")
		if t:
			res.append((t, f))
			prev_space = t.endswith(" ")
	if res and res[-1][0] != "\n":
		res[-1] = (res[-1][0].rstrip(" "), res[-1][1])
	return [s for s in res if s[0]]


def _rpr(f):
	parts = []
	if f.get("b"):
		parts.append("<w:b/><w:bCs/>")
	if f.get("i"):
		parts.append("<w:i/><w:iCs/>")
	parts.append(f'<w:sz w:val="{f["sz"]}"/><w:szCs w:val="{f["sz"]}"/>')
	if f.get("u"):
		parts.append('<w:u w:val="single"/>')
	return "".join(parts)


def _run(text, f):
	if text == "\n":
		return f"<w:r><w:rPr>{_rpr(f)}</w:rPr><w:br/></w:r>"
	return f'<w:r><w:rPr>{_rpr(f)}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


# ---------------------------------------------------------------------------
# Các phần cố định của gói .docx
# ---------------------------------------------------------------------------


def _document_xml(body, cfg):
	m = cfg["margins"]
	sect = (
		f'<w:sectPr><w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}" w:code="9"/>'
		f'<w:pgMar w:top="{m["top"]}" w:right="{m["right"]}" w:bottom="{m["bottom"]}" w:left="{m["left"]}" '
		'w:header="720" w:footer="720" w:gutter="0"/><w:cols w:space="720"/><w:docGrid w:linePitch="360"/></w:sectPr>'
	)
	return (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		f'<w:document xmlns:w="{W_NS}" '
		'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
		f"<w:body>{''.join(body)}{sect}</w:body></w:document>"
	)


def _core_xml(title):
	now = now_datetime().strftime("%Y-%m-%dT%H:%M:%SZ")
	return (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
		'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
		'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
		f"<dc:title>{escape(title)}</dc:title><dc:creator>{escape(frappe.session.user or '')}</dc:creator>"
		f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
		f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
		"</cp:coreProperties>"
	)


CONTENT_TYPES_XML = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
	'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
	'<Default Extension="xml" ContentType="application/xml"/>'
	'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
	'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
	'<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
	'<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
	'<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
	'<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
	"</Types>"
)

ROOT_RELS_XML = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
	'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
	'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
	'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
	"</Relationships>"
)

DOCUMENT_RELS_XML = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
	'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
	'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
	'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
	"</Relationships>"
)

_TNR = '<w:rFonts w:ascii="Times New Roman" w:eastAsia="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'

STYLES_XML = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	f'<w:styles xmlns:w="{W_NS}">'
	"<w:docDefaults>"
	f'<w:rPrDefault><w:rPr>{_TNR}<w:sz w:val="{BASE_SZ}"/><w:szCs w:val="{BASE_SZ}"/>'
	'<w:lang w:val="vi-VN" w:eastAsia="en-US" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>'
	'<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
	"</w:docDefaults>"
	'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
	'<w:pPr><w:jc w:val="both"/></w:pPr></w:style>'
	'<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/>'
	'<w:uiPriority w:val="1"/><w:semiHidden/><w:unhideWhenUsed/></w:style>'
	'<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/>'
	'<w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/>'
	'<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
	'<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
	'<w:style w:type="numbering" w:default="1" w:styleId="NoList"><w:name w:val="No List"/>'
	'<w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/></w:style>'
	"</w:styles>"
)

SETTINGS_XML = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	f'<w:settings xmlns:w="{W_NS}">'
	'<w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/>'
	'<w:characterSpacingControl w:val="doNotCompress"/>'
	'<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
	"</w:settings>"
)

# Gạch đầu dòng "-" giống file mẫu: left=720, hanging=360
NUMBERING_XML = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	f'<w:numbering xmlns:w="{W_NS}">'
	'<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/>'
	'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="-"/><w:lvlJc w:val="left"/>'
	'<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>'
	'<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:hint="default"/></w:rPr>'
	"</w:lvl></w:abstractNum>"
	'<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
	"</w:numbering>"
)

APP_XML = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
	"<Application>Vinatex HRM</Application></Properties>"
)

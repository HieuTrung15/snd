# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import csv
import traceback
from datetime import datetime

import frappe
from frappe.utils.file_manager import save_file
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# ============================
# CẤU HÌNH
# ============================

# Đường dẫn dữ liệu đã tải về máy chủ Ubuntu
ATTACH_ROOT = "/home/frappe/Lists_Attachments"
ATTACH_CSV  = os.path.join(ATTACH_ROOT, "attachments_map.csv")
META_CSV    = "/home/frappe/Lists_Attachments/metadata_master.csv"  # đổi nếu bạn để chỗ khác

# Doctype đích
TARGET_DOCTYPE = "VNT Document Management"

# Employee placeholder (PHẢI tồn tại trong hệ thống)
# → đã đổi sang nhân sự mã VGT00165 (Nguyễn Thị Mai Anh)
DEFAULT_IMPORT_EMPLOYEE = "VGT00165"

# Map cột trong metadata_master.csv -> fieldname của Doctype
FIELD_MAP = {
    "reference_number": "reference_number",   # Số hiệu văn bản *
    "summary": "summary",                     # Trích yếu *
    "document_date": "document_date",         # Ngày văn bản *
    "received_date": "received_date",         # Ngày đến *
    "sender": "sender",                       # Nơi gửi *
    "handler": "handler",                     # Người xử lý (text) - dùng để suy ra employee
}

# Tùy chọn chạy
DRY_RUN = False           # True: chỉ log, không ghi DB
COMMIT_EVERY = 50         # Commit mỗi N items
LOG_MISSING_FILE = True   # Log khi thiếu file vật lý


# ============================
# HÀM HỖ TRỢ
# ============================

def ensure_custom_fields():
    """Tạo 3 custom fields nếu chưa có: legacy_id, list_title, source_url."""
    fields = {
        TARGET_DOCTYPE: [
            dict(fieldname="legacy_id", label="Legacy ID", fieldtype="Int", insert_after="attach"),
            dict(fieldname="list_title", label="List Title", fieldtype="Data", insert_after="legacy_id"),
            dict(fieldname="source_url", label="Source URL", fieldtype="Data", options="URL", insert_after="list_title"),
        ]
    }
    try:
        create_custom_fields(fields, ignore_validate=True)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()


def check_default_employee():
    """Đảm bảo DEFAULT_IMPORT_EMPLOYEE tồn tại."""
    if not frappe.db.exists("Employee", DEFAULT_IMPORT_EMPLOYEE):
        raise Exception(
            f"DEFAULT_IMPORT_EMPLOYEE '{DEFAULT_IMPORT_EMPLOYEE}' không tồn tại. "
            f"Vui lòng tạo hoặc đổi mã cho khớp nhân sự thực tế."
        )


def to_date(s: str | None) -> str | None:
    """Parse nhiều định dạng ngày → ISO (YYYY-MM-DD)."""
    if not s:
        return None
    s = str(s).strip()
    fmts = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y")
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return None


def coalesce_date(*vals) -> str | None:
    """Trả về ISO date đầu tiên parse được trong danh sách."""
    for v in vals:
        d = to_date(v)
        if d:
            return d
    return None


def load_metadata() -> dict[tuple[str, str], dict]:
    """Đọc metadata_master.csv → dict[(ListTitle, ID)] = row(dict)."""
    meta = {}
    with open(META_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            key = ((r.get("ListTitle") or "").strip(), str(r.get("ID") or "").strip())
            if not key[0] or not key[1]:
                continue
            meta[key] = r
    return meta


def load_attachments() -> dict[tuple[str, str], list[dict]]:
    """Đọc attachments_map.csv → dict[(ListTitle, ItemID)] = list file info."""
    data = {}
    with open(ATTACH_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            lt = (r.get("ListTitle") or "").strip()
            iid = str(r.get("ItemID") or "").strip()
            fn = (r.get("FileName") or "").strip()
            abs_url = (r.get("AbsoluteUrl") or "").strip()
            if not (lt and iid and fn):
                frappe.logger().warning(f"Skip bad row in attachments_map.csv: {r}")
                continue
            local_path = os.path.join(ATTACH_ROOT, lt, f"ID-{iid}", fn)
            data.setdefault((lt, iid), []).append({
                "file_name": fn,
                "abs_url": abs_url,
                "local_path": local_path
            })
    return data


def resolve_employee(handler_text: str | None) -> str:
    """Suy ra Employee.name từ text 'handler'; nếu không có → dùng DEFAULT_IMPORT_EMPLOYEE."""
    if not handler_text:
        return DEFAULT_IMPORT_EMPLOYEE
    handler_text = str(handler_text).strip()
    if frappe.db.exists("Employee", handler_text):
        return handler_text
    emp = frappe.db.get_value(
        "Employee", filters={"employee_name": ["like", handler_text]}, fieldname="name"
    )
    if emp:
        return emp
    user_emp = None
    if "@" in handler_text:
        user_emp = frappe.db.get_value("Employee", {"user_id": handler_text}, "name")
    else:
        user_emp = frappe.db.get_value("Employee", {"user_id": handler_text}, "name")
    if user_emp:
        return user_emp
    return DEFAULT_IMPORT_EMPLOYEE


def ensure_required_defaults(doc, metadata: dict, list_title: str, item_id: str):
    """Đảm bảo các field bắt buộc có giá trị."""
    if not getattr(doc, "employee", None):
        doc.employee = resolve_employee(metadata.get("handler") or doc.get("handler"))
    doc.date = coalesce_date(
        metadata.get("received_date"),
        metadata.get("document_date"),
        datetime.today().date().isoformat(),
    )
    if not doc.document_date:
        doc.document_date = to_date(metadata.get("document_date")) or doc.date
    if not doc.received_date:
        doc.received_date = to_date(metadata.get("received_date")) or doc.date
    if not doc.sender:
        doc.sender = "Không rõ (legacy import)"
    if not doc.reference_number:
        doc.reference_number = f"{list_title}-{item_id}"
    if not doc.summary:
        doc.summary = "Chưa rõ (legacy import)"


def get_or_create_doc(list_title: str, item_id: str, metadata: dict):
    """Tạo (hoặc lấy) record theo (list_title + legacy_id)."""
    name = frappe.db.get_value(
        TARGET_DOCTYPE,
        filters={"legacy_id": item_id, "list_title": list_title},
        fieldname="name",
    )
    if name:
        return frappe.get_doc(TARGET_DOCTYPE, name), False
    doc = frappe.new_doc(TARGET_DOCTYPE)
    doc.update({"legacy_id": item_id, "list_title": list_title})
    for src, dst in FIELD_MAP.items():
        v = metadata.get(src)
        if src in ("document_date", "received_date"):
            v = to_date(v)
        doc.set(dst, v)
    ensure_required_defaults(doc, metadata, list_title, item_id)
    if not DRY_RUN:
        doc.insert(ignore_permissions=True)
    return doc, True


def attach_files(doc, files: list[dict]):
    """Attach toàn bộ file; file đầu → field attach; lưu URL gốc nếu có."""
    first_source_url = None
    for i, f in enumerate(files):
        path = f["local_path"]
        if not os.path.exists(path):
            if LOG_MISSING_FILE:
                frappe.logger().warning(f"Missing file: {path}")
            continue
        if DRY_RUN:
            continue
        with open(path, "rb") as fh:
            file_doc = save_file(f["file_name"], fh.read(), doc.doctype, doc.name, is_private=1)
            if f.get("abs_url"):
                first_source_url = first_source_url or f.get("abs_url")
            if i == 0 and not getattr(doc, "attach", None):
                doc.db_set("attach", file_doc.file_url)
    if (not DRY_RUN) and first_source_url and not getattr(doc, "source_url", None):
        try:
            doc.db_set("source_url", first_source_url)
        except Exception:
            pass


# ============================
# LUỒNG CHẠY CHÍNH
# ============================

def run_import():
    ensure_custom_fields()
    check_default_employee()
    meta = load_metadata()
    atts = load_attachments()
    total = len(atts)
    done = 0
    errors = 0
    for idx, ((list_title, item_id), files) in enumerate(atts.items(), start=1):
        try:
            md = meta.get((list_title, item_id), {})
            doc, created = get_or_create_doc(list_title, item_id, md)
            attach_files(doc, files)
            done += 1
            action = "CREATED" if created else "UPDATED"
            print(f"[{idx}/{total}] {action}: {list_title} / ID={item_id} -> {doc.name}")
            if not DRY_RUN and (idx % COMMIT_EVERY == 0):
                frappe.db.commit()
        except Exception:
            errors += 1
            print(f"[{idx}/{total}] ERROR at {list_title} / ID={item_id}")
            traceback.print_exc()
            frappe.db.rollback()
    if not DRY_RUN:
        frappe.db.commit()
    print(f"=== DONE: {done}/{total} items, errors: {errors} ===")


def execute():
    run_import()

# -*- coding: utf-8 -*-
"""
Đồng bộ trực tiếp SharePoint Online → ERPNext (VNT Document Management)
- Lấy metadata theo Display Name (tự resolve InternalName)
- Tải file đính kèm AttachmentFiles và đẩy thẳng vào File (private)
- Idempotent theo (legacy_id + list_title)
- Incremental sync: lọc theo Modified >= last_run (CAML)
"""
import os, io
from datetime import datetime, timezone

import frappe
from dotenv import dotenv_values
from msal import ConfidentialClientApplication
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.token_response import TokenResponse
from office365.sharepoint.listitems.caml.query import CamlQuery
from frappe.utils.file_manager import save_file

TARGET_DOCTYPE = "VNT Document Management"
# === CONFIG PATHS (điền site name của bạn) ===SITE_NAME = "<SITE_NAME>"  
# TODO: đổi thành site thật, ví dụ "vnt.local"
ENV_PATH = f"/home/frappe/frappe-bench/sites/ihrm.vinatex.com.vn/private/vnt_sharepoint.env"
CHECKPOINT_PATH = f"/home/frappe/frappe-bench/sites/ihrm.vinatex.com.vn/private/vnt_spo_checkpoint.txt"
# === Load ENV (bí mật) ===
CFG = dotenv_values(ENV_PATH)
TENANT_ID        = CFG["TENANT_ID"]
CLIENT_ID        = CFG["CLIENT_ID"]
CLIENT_SECRET    = CFG["CLIENT_SECRET"]
SITE_HOSTNAME    = CFG["SITE_HOSTNAME"]
SITE_RELATIVE_URL= CFG["SITE_RELATIVE_URL"]

DISPLAY_MAP = {
    "reference_number": CFG.get("REF_NUMBER_DISPLAY", "Số hiệu VB"),
    "summary":          CFG.get("SUMMARY_DISPLAY", "Trích yếu"),
    "document_date":    CFG.get("DOCDATE_DISPLAY", "Ngày văn bản"),
    "received_date":    CFG.get("RECVDATE_DISPLAY", "Ngày đến"),
    "sender":           CFG.get("SENDER_DISPLAY", "Nơi gửi"),
    "handler":          CFG.get("HANDLER_DISPLAY", "Người xử lý"),
}

FIELD_MAP = {
    "reference_number": "reference_number",
    "summary": "summary",
    "document_date": "document_date",
    "received_date": "received_date",
    "sender": "sender",
    "handler": "handler",
}

DATE_INPUT_FORMATS = ("%Y-%m-%d","%d/%m/%Y","%m/%d/%Y","%d-%m-%Y","%d.%m.%Y")
# def spo_context():
#     site_url = f"https://{SITE_HOSTNAME}{SITE_RELATIVE_URL}"
#     creds = ClientCredential(CLIENT_ID, CLIENT_SECRET)     # AAD app-only
#     ctx = ClientContext(site_url).with_credentials(creds)
#     return ctx

def spo_context():
    site_url = f"https://{SITE_HOSTNAME}{SITE_RELATIVE_URL}"
    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )

    # Hàm cấp token MỖI LẦN được SDK gọi
    def token_provider():
        tok = app.acquire_token_for_client(scopes=[f"https://{SITE_HOSTNAME}/.default"])
        if "access_token" not in tok:
            raise Exception(f"MSAL error: {tok.get('error')} | {tok.get('error_description')}")
        # Trả về TokenResponse để SDK biết thời điểm hết hạn (expiresIn)
        return TokenResponse.from_json(tok)

    # QUAN TRỌNG: truyền callable, không phải chuỗi
    return ClientContext(site_url).with_access_token(token_provider)

def to_iso_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    # chỉ return s khi đã thử hết format
    return s

def read_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                line = f.read().strip()
                if line:
                    return line
        except Exception:
            pass
    # fallback: FIRST_SYNC_SINCE trong .env
    return CFG.get("FIRST_SYNC_SINCE", None)

def write_checkpoint(ts_iso):
    try:
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            f.write(ts_iso)
    except Exception:
        pass

def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def get_sp_list(ctx, identifier: str):
    # Nếu bắt đầu bằng "/", coi như server-relative path → dùng get_list
    return ctx.web.get_list(identifier) if identifier.startswith("/") else ctx.web.lists.get_by_title(identifier)

def get_field_internal_map(ctx, list_identifier):
    sp_list = get_sp_list(ctx, list_identifier)
    fields = sp_list.fields.get().execute_query()
    result = {}
    for f in fields:
        title = getattr(f, "title", None)
        internal = getattr(f, "internal_name", None) or getattr(f, "internalName", None)
        if title and internal:
            result[str(title)] = str(internal)
    return result

def caml_query_modified_since(modified_since_iso, internal_fields, row_limit=2000):
    """
    Xây CAML query lọc Modified >= modified_since.
    internal_fields: danh sách InternalName cần load (ngoài ID, Modified)
    """
    # SharePoint field 'Modified' là DateTime    
    view_fields = "".join([f"<FieldRef Name='{fn}' />" for fn in (["ID","Modified"] + internal_fields)]) 
    where = ""
    if modified_since_iso:
        where = f"""
        <Where>
            <Geq>
              <FieldRef Name='Modified' />
              <Value IncludeTimeValue='TRUE' Type='DateTime'>{modified_since_iso}</Value>
            </Geq>
        </Where>
        """
    view_xml = f"""
    <View Scope='RecursiveAll'>
      <ViewFields>{view_fields}</ViewFields>
      {where}      <RowLimit>{row_limit}</RowLimit>
    </View>
    """
    q = CamlQuery()
    q.view_xml = view_xml
    return q

def fetch_list_items(ctx, list_identifier, internal_needed, modified_since_iso=None):
    sp_list = get_sp_list(ctx, list_identifier)
    query = caml_query_modified_since(modified_since_iso, internal_needed)
    items = sp_list.get_items(query).execute_query()
    for it in items:
        props = it.properties or {}
        modified_dt = props.get("Modified")
        modified_iso = modified_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(modified_dt, "strftime") else None
        values = {iname: props.get(iname) for iname in internal_needed}
        yield int(props.get("ID")), modified_iso, values

def fetch_attachments(ctx, list_identifier, item_id):
    sp_list = get_sp_list(ctx, list_identifier)
    item = sp_list.items.get_by_id(item_id)
    atts = item.attachment_files.get().execute_query()
    files = []
    for a in atts:
        file = ctx.web.get_file_by_server_relative_url(a.serverRelativeUrl)
        file.download().execute_query()
        content_bytes = file.context.pending_request._downloaded_content
        files.append({
            "name": a.file_name,
            "server_relative_url": a.serverRelativeUrl,
            "content": content_bytes
        })
    return files

def ensure_doc(list_title, item_id, meta_by_key):
    name = frappe.db.get_value(TARGET_DOCTYPE, {"legacy_id": str(item_id), "list_title": list_title}, "name")
    if name:
        doc = frappe.get_doc(TARGET_DOCTYPE, name)
    else:
        doc = frappe.new_doc(TARGET_DOCTYPE)
        doc.update({"legacy_id": str(item_id), "list_title": list_title})

    for src, dst in FIELD_MAP.items():
        v = meta_by_key.get(src)
        if src in ("document_date","received_date"):
            v = to_iso_date(v)
        doc.set(dst, v)

    if doc.name:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc

def attach_files(doc, attachments):
    first_source_url = None
    for i, f in enumerate(attachments):
        file_doc = save_file(f["name"], f["content"], doc.doctype, doc.name, is_private=1)
        abs_url = f"https://{SITE_HOSTNAME}{f['server_relative_url']}"
        file_doc.source = abs_url
        file_doc.save(ignore_permissions=True)

        if i == 0 and not getattr(doc, "attach", None):
            doc.attach = file_doc.file_url
            first_source_url = abs_url

    if first_source_url and not getattr(doc, "source_url", None):
        doc.source_url = first_source_url

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    
def run_sync(list_titles=None, limit_per_list=None, incremental=True, override_since=None):
    """
    list_titles: danh sách list cần đồng bộ. None => dùng preset bên dưới.
    limit_per_list: giới hạn số item mỗi list (test).
    incremental: True => lọc Modified >= last_run (hoặc FIRST_SYNC_SINCE). False => full.
    override_since: ISO string để ép mốc đồng bộ (ví dụ "2024-01-01T00:00:00Z").
    """
    ctx = spo_context()

    # Preset list (bạn sửa cho khớp thực tế)
    if not list_titles:
        list_titles = [
            "VT đến- CQ (2023-2024)",
            "VT đến- CQ (2025-2026)",
            "VT đi CQ (2023-2024)",
            "VT đi CQ (2025-2026)",
            "QĐ-CQ (2023-2026)",
        ]

    # Mốc thời gian incremental
    since = None
    if incremental:
        since = override_since or read_checkpoint()

    # thời điểm bắt đầu chạy (để ghi checkpoint cuối cùng)
    run_started_iso = now_utc_iso()
    print(f"[SYNC] incremental={incremental} since={since} at={run_started_iso}")

    for lt in list_titles:
        disp2internal = get_field_internal_map(ctx, lt)
        internal_needed = [disp2internal.get(d) for d in DISPLAY_MAP.values() if disp2internal.get(d)]
        print(f"[SYNC] List: {lt} | fields: {internal_needed} | since={since or 'FULL'}")

        count = 0
        for item_id, modified_iso, values in fetch_list_items(ctx, lt, internal_needed, modified_since_iso=since):
            # map metadata theo key chuẩn
            md = {}
            for key, disp in DISPLAY_MAP.items():
                internal = disp2internal.get(disp)
                if internal:
                    md[key] = values.get(internal)

            doc = ensure_doc(lt, item_id, md)
            atts = fetch_attachments(ctx, lt, item_id)
            attach_files(doc, atts)
            count += 1
            print(f"  -> Imported ID={item_id} (Modified={modified_iso}) → {doc.name}")

            if limit_per_list and count >= int(limit_per_list):
                break

    # Ghi checkpoint: mốc an toàn là thời điểm bắt đầu chạy (tránh bỏ sót update trong lúc sync)
    if incremental:
        write_checkpoint(run_started_iso)
        print(f"[SYNC] checkpoint saved: {run_started_iso}")

def execute():
    run_sync()

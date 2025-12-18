# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlencode

import frappe
import requests
from frappe.utils.password import set_encrypted_password

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SETTINGS_DOCTYPE = "VNT Teams URL"
LOG_DOCTYPE = "VNT Teams Message Log"
LOG_NAMING_SERIES = "VTMSG-.YYYY.-.MM.-.####"

# Cache keys (Redis via frappe.cache)
CACHE_TOKEN_KEY = "vnt_teams_graph:access_token"
CACHE_TOKEN_EXP_KEY = "vnt_teams_graph:access_token_exp"
CACHE_CHAT_KEY_PREFIX = "vnt_teams_graph:chat_id:"  # + target_user_id or upn
CACHE_USER_KEY_PREFIX = "vnt_teams_graph:user_id:"  # + upn/email


@dataclass
class TeamsSettings:
    name: str
    auth_url: str
    access_token_url: str
    client_id: str
    client_secret: str
    me_id: str
    scope: str
    refresh_token: str
    callback_url: Optional[str] = None


def _get_latest_settings_docname() -> str:
    rows = frappe.get_all(
        SETTINGS_DOCTYPE,
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )
    if not rows:
        frappe.throw(
            f"Chưa có bản ghi cấu hình trong DocType '{SETTINGS_DOCTYPE}'. "
            f"Vào ERPNext tạo 1 record và điền client_id/client_secret/me_id/scope/refresh_token."
        )
    return rows[0]["name"]


def get_settings(docname: Optional[str] = None) -> TeamsSettings:
    docname = docname or _get_latest_settings_docname()
    doc = frappe.get_doc(SETTINGS_DOCTYPE, docname)

    # Password fields: use get_password()
    client_secret = doc.get_password("client_secret") or ""
    refresh_token = doc.get_password("refresh_token", raise_exception=False) or ""

    # Basic validation
    missing = []
    for k in ("auth_url", "access_token_url", "client_id", "me_id", "scope"):
        if not (doc.get(k) or "").strip():
            missing.append(k)
    if not client_secret:
        missing.append("client_secret")
    if not refresh_token:
        missing.append("refresh_token")
    if missing:
        frappe.throw(
            f"Thiếu cấu hình Teams/Graph trong '{SETTINGS_DOCTYPE}' ({docname}): {', '.join(missing)}"
        )

    return TeamsSettings(
        name=docname,
        auth_url=doc.auth_url.strip(),
        access_token_url=doc.access_token_url.strip(),
        client_id=doc.client_id.strip(),
        client_secret=client_secret,
        me_id=doc.me_id.strip(),
        scope=doc.scope.strip(),
        refresh_token=refresh_token,
        callback_url=(doc.callback_url.strip() if (doc.get("callback_url") or "").strip() else None),
    )


def _cache() -> "frappe.utils.redis_wrapper.RedisWrapper":
    return frappe.cache()


def _decode_cache_value(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="ignore")
    return str(v)


def _cache_set_value(key: str, value: str, ttl_sec: int) -> None:
    try:
        c = _cache()
        try:
            c.set_value(key, value, expires_in_sec=ttl_sec)
        except TypeError:
            c.set_value(key, value, expires_in=ttl_sec)
    except Exception:
        # cache hỏng thì vẫn cho flow chạy tiếp (chỉ mất lợi ích cache)
        pass


def _get_cached_token() -> Tuple[Optional[str], int]:
    c = _cache()

    token = c.get_value(CACHE_TOKEN_KEY)
    exp = c.get_value(CACHE_TOKEN_EXP_KEY)

    token = _decode_cache_value(token)
    exp = _decode_cache_value(exp)

    try:
        exp_i = int(exp) if exp else 0
    except Exception:
        exp_i = 0

    return token, exp_i



def _set_cached_token(token: str, expires_at_unix: int) -> None:
    c = _cache()
    ttl = max(60, expires_at_unix - int(time.time()) - 30)

    try:
        c.set_value(CACHE_TOKEN_KEY, token, expires_in_sec=ttl)
        c.set_value(CACHE_TOKEN_EXP_KEY, str(expires_at_unix), expires_in_sec=ttl)
    except TypeError:
        # một số version frappe dùng expires_in thay vì expires_in_sec
        c.set_value(CACHE_TOKEN_KEY, token, expires_in=ttl)
        c.set_value(CACHE_TOKEN_EXP_KEY, str(expires_at_unix), expires_in=ttl)
    except Exception:
        # cache hỏng thì vẫn cho flow chạy tiếp (sẽ refresh mỗi lần)
        pass


def _http() -> requests.Session:
    """
    Reuse HTTP connections (TLS/keep-alive) để giảm latency khi gọi Graph.
    Session được gắn vào frappe.local để tránh dùng chung giữa threads.
    """
    sess = getattr(frappe.local, "vnt_teams_graph_http", None)
    if sess is None:
        sess = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        frappe.local.vnt_teams_graph_http = sess
    return sess


def _log_message_send(
    *,
    to_upn_or_email: Optional[str],
    chat_id: Optional[str],
    message: str,
    settings_docname: Optional[str],
    status: str,
    duration_ms: Optional[int] = None,
    total_ms: Optional[int] = None,
    token_ms: Optional[int] = None,
    user_lookup_ms: Optional[int] = None,
    chat_ms: Optional[int] = None,
    send_ms: Optional[int] = None,
    http_status: Optional[int] = None,
    graph_message_id: Optional[str] = None,
    response: Any = None,
    error: Optional[str] = None,
) -> None:
    """
    Ghi log mọi lần gửi tin (success/fail). Không làm fail flow chính nếu log lỗi.
    """
    try:
        payload = {
            "doctype": LOG_DOCTYPE,
            "naming_series": LOG_NAMING_SERIES,
            "send_time": frappe.utils.now_datetime(),
            "settings": settings_docname,
            "to_upn_or_email": to_upn_or_email,
            "chat_id": chat_id,
            "message": message,
            "status": status,
            "duration_ms": duration_ms,
            "total_ms": total_ms,
            "token_ms": token_ms,
            "user_lookup_ms": user_lookup_ms,
            "chat_ms": chat_ms,
            "send_ms": send_ms,
            "http_status": http_status,
            "graph_message_id": graph_message_id,
            "response_json": (
                json.dumps(response, ensure_ascii=False, default=str) if response is not None else None
            ),
            "error": error,
        }

        # Không commit trong transaction của caller.
        # - Production: enqueue vào worker (commit độc lập).
        # - Bench console: chạy ngay và commit để user thấy log ngay.
        if getattr(frappe.flags, "in_console", False):
            _insert_message_log(payload)
        else:
            frappe.enqueue(
                "vinatex.integrations.teams_graph._insert_message_log",
                queue="default",
                timeout=120,
                is_async=True,
                enqueue_after_commit=False,
                payload=payload,
            )
    except Exception:
        try:
            frappe.log_error(frappe.get_traceback(), "VNT Teams Message Log insert failed")
        except Exception:
            pass


def _insert_message_log(payload: Dict[str, Any]) -> None:
    doc = frappe.get_doc(payload)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()


def _update_refresh_token_in_db(docname: str, new_refresh_token: str) -> None:
    if not new_refresh_token:
        return
    set_encrypted_password("VNT Teams URL", docname, new_refresh_token, fieldname="refresh_token")
    frappe.db.set_value("VNT Teams URL", docname, "refresh_token", "*****", update_modified=False)
    frappe.db.commit()


def refresh_access_token(settings: TeamsSettings) -> Dict[str, Any]:
    """
    Uses refresh_token to obtain new access_token.
    Handles refresh_token rotation (if provided by server).
    """
    data = {
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "grant_type": "refresh_token",
        "refresh_token": settings.refresh_token,
        # v2.0 expects scopes (space-separated)
        "scope": settings.scope,
    }

    resp = _http().post(settings.access_token_url, data=data, timeout=30)
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}

    if resp.status_code >= 400:
        # Typical: invalid_grant / interaction_required when refresh token is revoked/expired by CA
        err = payload.get("error") if isinstance(payload, dict) else None
        desc = payload.get("error_description") if isinstance(payload, dict) else None
        frappe.throw(
            f"Refresh token thất bại ({resp.status_code}). error={err} desc={desc or payload}. "
            f"Nếu là 'invalid_grant' hoặc 'interaction_required' thì cần login lại để lấy refresh_token mới."
        )

    # rotate refresh token if returned
    new_rt = payload.get("refresh_token")
    if new_rt and new_rt != settings.refresh_token:
        _update_refresh_token_in_db(settings.name, new_rt)
        settings.refresh_token = new_rt

    access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in") or 3600)
    if not access_token:
        frappe.throw(f"Không nhận được access_token từ token endpoint. Payload={payload}")

    expires_at = int(time.time()) + expires_in
    _set_cached_token(access_token, expires_at)

    return payload


def get_access_token(settings: Optional[TeamsSettings] = None, force_refresh: bool = False) -> str:
    settings = settings or get_settings()

    if not force_refresh:
        token, exp = _get_cached_token()
        if token and exp and (exp - int(time.time()) > 120):
            return token

    payload = refresh_access_token(settings)

    # Ưu tiên đọc cache (nếu cache hoạt động)
    token, exp = _get_cached_token()
    if token:
        return token

    # Fallback: trả thẳng access_token vừa refresh được
    token2 = payload.get("access_token")
    if token2:
        return token2

    frappe.throw("Không lấy được access_token sau khi refresh (cache miss + payload thiếu access_token).")



def _graph_request(method: str, url: str, token: str, json_body: Any = None, retry_on_401: bool = True) -> requests.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    resp = _http().request(method, url, headers=headers, json=json_body, timeout=30)

    # If token expired/revoked, refresh once then retry
    if resp.status_code == 401 and retry_on_401:
        token2 = get_access_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token2}"
        resp = _http().request(method, url, headers=headers, json=json_body, timeout=30)

    return resp


def _user_cache_key(upn_or_email: str) -> str:
    return f"{CACHE_USER_KEY_PREFIX}{upn_or_email}".lower()


def get_cached_user_id(upn_or_email: str) -> Optional[str]:
    v = _cache().get_value(_user_cache_key(upn_or_email))
    return _decode_cache_value(v)


def set_cached_user_id(upn_or_email: str, user_id: str, ttl_days: int = 30) -> None:
    _cache_set_value(_user_cache_key(upn_or_email), user_id, ttl_days * 86400)


def get_user_id_by_upn(
    upn_or_email: str,
    settings: Optional[TeamsSettings] = None,
    *,
    token: Optional[str] = None,
) -> str:
    settings = settings or get_settings()
    cached = get_cached_user_id(upn_or_email)
    if cached:
        return cached

    token = token or get_access_token(settings)
    url = f"{GRAPH_BASE}/users/{upn_or_email}?$select=id,displayName,userPrincipalName,mail"

    resp = _graph_request("GET", url, token)
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        frappe.throw(f"Không lấy được user id cho '{upn_or_email}'. HTTP {resp.status_code}: {payload}")

    user_id = resp.json()["id"]
    set_cached_user_id(upn_or_email, user_id, ttl_days=30)
    return user_id


def _chat_cache_key(target_user_id_or_upn: str) -> str:
    return f"{CACHE_CHAT_KEY_PREFIX}{target_user_id_or_upn}"


def get_cached_chat_id(target_user_id_or_upn: str) -> Optional[str]:
    v = _cache().get_value(_chat_cache_key(target_user_id_or_upn))
    return _decode_cache_value(v)


def set_cached_chat_id(target_user_id_or_upn: str, chat_id: str, ttl_days: int = 30) -> None:
    _cache_set_value(_chat_cache_key(target_user_id_or_upn), chat_id, ttl_days * 86400)


def get_or_create_one_on_one_chat(
    target_user_id: str,
    settings: Optional[TeamsSettings] = None,
    *,
    token: Optional[str] = None,
) -> str:
    """
    Create (or return existing) 1:1 chat between service account (me_id) and target.
    Graph is effectively idempotent for oneOnOne between same 2 users.
    """
    settings = settings or get_settings()

    # cache by target_user_id
    cached = get_cached_chat_id(target_user_id)
    if cached:
        return cached

    token = token or get_access_token(settings)

    body = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"{GRAPH_BASE}/users('{settings.me_id}')",
            },
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"{GRAPH_BASE}/users('{target_user_id}')",
            },
        ],
    }

    url = f"{GRAPH_BASE}/chats"
    resp = _graph_request("POST", url, token, json_body=body)

    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        frappe.throw(f"Tạo/lấy chat 1:1 thất bại. HTTP {resp.status_code}: {payload}")

    chat_id = resp.json().get("id")
    if not chat_id:
        frappe.throw(f"Tạo chat thành công nhưng không có 'id' trong response: {resp.json()}")

    set_cached_chat_id(target_user_id, chat_id, ttl_days=60)
    return chat_id


def send_chat_message(
    chat_id: str,
    content: str,
    settings: Optional[TeamsSettings] = None,
    *,
    to_upn_or_email: Optional[str] = None,
    settings_docname: Optional[str] = None,
    token: Optional[str] = None,
    token_ms: Optional[int] = None,
    user_lookup_ms: Optional[int] = None,
    chat_ms: Optional[int] = None,
    total_start: Optional[float] = None,
) -> Dict[str, Any]:
    settings = settings or get_settings()
    token = token or get_access_token(settings)

    body = {
        "body": {"content": content}
    }
    url = f"{GRAPH_BASE}/chats/{chat_id}/messages"

    start = time.time()
    try:
        resp = _graph_request("POST", url, token, json_body=body)
    except Exception:
        send_ms = int((time.time() - start) * 1000)
        _log_message_send(
            to_upn_or_email=to_upn_or_email,
            chat_id=chat_id,
            message=content,
            settings_docname=settings_docname or settings.name,
            status="Failure",
            duration_ms=send_ms,
            send_ms=send_ms,
            token_ms=token_ms,
            user_lookup_ms=user_lookup_ms,
            chat_ms=chat_ms,
            total_ms=(int((time.time() - total_start) * 1000) if total_start else None),
            error=frappe.get_traceback(),
        )
        raise
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        send_ms = int((time.time() - start) * 1000)
        _log_message_send(
            to_upn_or_email=to_upn_or_email,
            chat_id=chat_id,
            message=content,
            settings_docname=settings_docname or settings.name,
            status="Failure",
            duration_ms=send_ms,
            send_ms=send_ms,
            token_ms=token_ms,
            user_lookup_ms=user_lookup_ms,
            chat_ms=chat_ms,
            total_ms=(int((time.time() - total_start) * 1000) if total_start else None),
            http_status=resp.status_code,
            response=payload,
        )
        frappe.throw(f"Gửi tin nhắn thất bại. HTTP {resp.status_code}: {payload}")

    payload = resp.json()
    send_ms = int((time.time() - start) * 1000)
    _log_message_send(
        to_upn_or_email=to_upn_or_email,
        chat_id=chat_id,
        message=content,
        settings_docname=settings_docname or settings.name,
        status="Success",
        duration_ms=send_ms,
        send_ms=send_ms,
        token_ms=token_ms,
        user_lookup_ms=user_lookup_ms,
        chat_ms=chat_ms,
        total_ms=(int((time.time() - total_start) * 1000) if total_start else None),
        http_status=resp.status_code,
        graph_message_id=(payload.get("id") if isinstance(payload, dict) else None),
        response=payload,
    )
    return payload


def notify_user(
    upn_or_email: str,
    message: str,
    settings_docname: Optional[str] = None,
) -> Dict[str, Any]:
    """
    High-level: email/UPN -> user_id -> chat_id -> send message
    """
    settings = get_settings(settings_docname)
    total_start = time.time()

    t0 = time.time()
    token = get_access_token(settings)
    token_ms = int((time.time() - t0) * 1000)

    try:
        t1 = time.time()
        target_id = get_user_id_by_upn(upn_or_email, settings=settings, token=token)
        user_lookup_ms = int((time.time() - t1) * 1000)

        t2 = time.time()
        chat_id = get_or_create_one_on_one_chat(target_id, settings=settings, token=token)
        chat_ms = int((time.time() - t2) * 1000)
    except Exception:
        _log_message_send(
            to_upn_or_email=upn_or_email,
            chat_id=None,
            message=message,
            settings_docname=settings.name,
            status="Failure",
            total_ms=int((time.time() - total_start) * 1000),
            token_ms=token_ms,
            error=frappe.get_traceback(),
        )
        raise

    return send_chat_message(
        chat_id,
        message,
        settings=settings,
        to_upn_or_email=upn_or_email,
        settings_docname=settings.name,
        token=token,
        token_ms=token_ms,
        user_lookup_ms=user_lookup_ms,
        chat_ms=chat_ms,
        total_start=total_start,
    )


@frappe.whitelist()
def notify_user_api(upn_or_email: str, message: str, settings_docname: Optional[str] = None) -> Dict[str, Any]:
    """
    Whitelisted wrapper: call from client/script.
    """
    # frappe.only_for("System Manager")  # chỉnh role nếu muốn
    return notify_user(upn_or_email, message, settings_docname=settings_docname)


@frappe.whitelist()
def enqueue_notify_user(upn_or_email: str, message: str, settings_docname: Optional[str] = None) -> str:
    """
    Background job: tránh chậm UI.
    """
    frappe.only_for("System Manager")  # chỉnh role nếu muốn

    job = frappe.enqueue(
        "vinatex.integrations.teams_graph.notify_user",
        queue="default",
        timeout=300,
        is_async=True,
        upn_or_email=upn_or_email,
        message=message,
        settings_docname=settings_docname,
    )
    return str(job) if job else "enqueued"


@frappe.whitelist()
def build_authorize_url(settings_docname: Optional[str] = None, state: Optional[str] = None) -> str:
    """
    Optional: build an authorize URL (for bootstrap to obtain new refresh_token via callback).
    Only useful if you implement your own callback endpoint in ERPNext.
    """
    settings = get_settings(settings_docname)
    if not settings.callback_url:
        frappe.throw("Chưa cấu hình callback_url trong VNT Teams URL.")

    # This assumes v2 authorize endpoint is stored in settings.auth_url
    qs = {
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": settings.callback_url,
        "response_mode": "query",
        "scope": settings.scope,
        "state": state or frappe.generate_hash(length=16),
    }
    return f"{settings.auth_url}?{urlencode(qs)}"


@frappe.whitelist()
def oauth_callback_store_refresh_token(code: str, settings_docname: Optional[str] = None) -> Dict[str, Any]:
    """
    Optional: exchange auth code for tokens, store refresh_token into DocType.
    Use only if you decide to bootstrap without Postman.
    """
    settings = get_settings(settings_docname)
    if not settings.callback_url:
        frappe.throw("Chưa cấu hình callback_url trong VNT Teams URL.")

    data = {
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.callback_url,
        "scope": settings.scope,
    }
    resp = requests.post(settings.access_token_url, data=data, timeout=30)
    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text}
    if resp.status_code >= 400:
        frappe.throw(f"Đổi code -> token thất bại. HTTP {resp.status_code}: {payload}")

    rt = payload.get("refresh_token")
    if not rt:
        frappe.throw(f"Không có refresh_token trong response (thiếu offline_access hoặc policy chặn). Payload={payload}")

    _update_refresh_token_in_db(settings.name, rt)
    # clear cache so next call uses fresh token
    _cache().delete_value(CACHE_TOKEN_KEY)
    _cache().delete_value(CACHE_TOKEN_EXP_KEY)

    return {"ok": True, "stored_in": settings.name}

# apps/vinatex/vinatex/patches/utils/rocket_chat.py

import frappe
from rocketchat_API.rocketchat import RocketChat
from urllib.parse import urlsplit, urlunsplit

SERVER_URL  = "http://14.225.164.136:3000"
# BOT_USER_ID = "coJbfrAQHpSK3Q4gh"    # User ID từ My Account → Profile
# BOT_TOKEN   = "PACpeEU-WnuBvzdclmCurNEYkU5jiRZAFoKgAfhYROw"      # Personal Access Token

BOT_TOKEN = "ZfYrSJG4uP2kwgYUkznpjvRzBJTVp8LZMSxkNx7bNUB"
BOT_USER_ID = "HPBAWPdZdETWatSig"

rocket = RocketChat(user_id=BOT_USER_ID, auth_token=BOT_TOKEN, server_url=SERVER_URL.rstrip("/"))

def send_rocket_message(to_users, message, link=None, title=None):
    """
    Gửi tin nhắn Rocket.Chat cho 1 hoặc nhiều user.

    - Có thể truyền:
        - "hieutt"
        - "hieutt@vinatex.com.vn"
        - "hieutt@vinatex.com.vn, hungbt"
        - ["hieutt"]
        - ["hieutt@vinatex.com.vn", "hungbt"]
        - [["hieutt", "hungbt"], "tanpv@vinatex.com.vn"]

    - Tự chuẩn hoá username Rocket.Chat:
        - Bỏ @ đầu
        - Nếu là email thì lấy phần trước @
    """

    # Bước 1: chuẩn hoá thành list thô (flatten 1 cấp)
    raw_list = []

    if isinstance(to_users, str):
        # Cho phép: "a,b;c"
        for part in to_users.replace(";", ",").split(","):
            part = part.strip()
            if part:
                raw_list.append(part)
    else:
        # là list/tuple/set/...: flatten 1 lớp
        for item in to_users:
            if not item:
                continue
            if isinstance(item, (list, tuple, set)):
                for sub in item:
                    if sub:
                        raw_list.append(str(sub))
            else:
                raw_list.append(str(item))

    # Bước 2: chuẩn hoá từng user về dạng username Rocket.Chat
    normalized_users = []
    for u in raw_list:
        u = u.strip()
        if not u:
            continue

        # bỏ @ đầu nếu có
        u = u.lstrip("@")

        # nếu là email thì lấy phần trước @
        if "@" in u:
            u = u.split("@", 1)[0]

        if u:
            normalized_users.append(u)

    # Optional: bỏ trùng
    normalized_users = list(dict.fromkeys(normalized_users))

    # Bước 3: build text
    sanitized_link = _sanitize_url(link)
    text = f"*{title}*\n{message}" if title else message
    if sanitized_link:
        text += f"\n➡️ [Xem chi tiết]({sanitized_link})"

    # Bước 4: gửi
    results = []
    for user in normalized_users:
        res = rocket.chat_post_message(text, channel=f"@{user}")
        results.append(res.json())

    return results


def _sanitize_url(link):
    """Loại bỏ port 8000 khỏi URL nếu có."""
    if not link:
        return link

    try:
        parts = urlsplit(link)
    except ValueError:
        return link

    if parts.port != 8000:
        return link

    netloc = parts.hostname or ""
    sanitized = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return sanitized or link



# chạy thử trên console
# from vinatex.patches.utils.rocket_chat import send_rocket_message
# import frappe

# send_rocket_message(
#     to_users=["hieutt", "sonph"],
#     title=":bell: Thông báo",
#     message="Đơn nghỉ phép HR-LAP-2025-00001 đã được duyệt.",
#     link=f"{frappe.utils.get_url()}/app/leave-application/HR-LAP-2025-00001"
# )




















# def _get_client():
#     """Tạo client RocketChat dùng chung."""
#     return RocketChat(
#         user_id=BOT_USER_ID,
#         auth_token=BOT_TOKEN,
#         server_url=SERVER_URL,
#     )


# def send_rocket_message(to_users, message, link=None):
#     """
#     Gửi tin nhắn Rocket.Chat cho 1 hoặc nhiều user.

#     Args:
#         to_users: "hieutt" hoặc ["hieutt", "hungbt"]
#         message: nội dung chính
#         link: URL ERPNext (tuỳ chọn)
#     """
#     rc = _get_client()

#     # chuẩn hoá danh sách user
#     if isinstance(to_users, str):
#         to_users = [
#             u.strip().lstrip("@")
#             for u in to_users.replace(";", ",").split(",")
#             if u.strip()
#         ]

#     text = message
#     if link:
#         text += f"\n➡️ [Mở trong ERPNext]({link})"

#     results = []
#     for user in to_users:
#         res = rc.chat_post_message(text, channel=f"@{user}")
#         # log nếu lỗi
#         try:
#             data = res.json()
#         except Exception:
#             data = {"status_code": res.status_code, "text": res.text}

#         if not data.get("success", False):
#             frappe.log_error(
#                 f"Rocket.Chat send failed for @{user}: {data}",
#                 "Rocket.Chat Notification",
#             )

#         results.append(data)

#     return results




# from rocketchat_API.rocketchat import RocketChat

# def send_rocket_message(
#     to_users,
#     message,
#     link=None,
#     server_url="http://14.225.164.136:3000",
#     bot_user_id="5igLZmhBsPzQstd2r",
#     bot_token="NKgDFj4YLp4I1nz5zXgaO739GSpiTSn1SCZDOmDjWFF",
# ):

#     rocket = RocketChat(
#         user_id=bot_user_id,
#         auth_token=bot_token,
#         server_url=server_url,
#     )

#     # chuẩn hoá list user
#     if isinstance(to_users, str):
#         to_users = [u.strip().lstrip("@") for u in to_users.replace(";", ",").split(",") if u.strip()]

#     text = message
#     if link:
#         text += f"\n➡️ [Mở trong ERPNext]({link})"

#     results = []
#     for user in to_users:
#         res = rocket.chat_post_message(text, channel=f"@{user}")
#         results.append(res)

#     return results

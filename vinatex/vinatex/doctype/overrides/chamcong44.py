# f18_export.py
import csv
import sys
from datetime import datetime
from typing import Optional

# ====== CẤU HÌNH THIẾT BỊ ======
DEVICE_IP   = "192.168.1.44"
DEVICE_PORT = 4370
COMM_KEY    = 123456       # mật khẩu/comm-key của thiết bị
TIMEOUT_S   = 10

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d"
]

def parse_dt(text: str) -> datetime:
    last_err = None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except Exception as e:
            last_err = e
    raise ValueError(f"Thời gian không hợp lệ: {text}. Ví dụ: 2025-09-01 08:00:00")

def ask_range() -> tuple[datetime, datetime]:
    if "--from" in sys.argv or "--to" in sys.argv:
        # đọc từ tham số dòng lệnh
        args = " ".join(sys.argv[1:])
        def get_arg(name: str) -> Optional[str]:
            tokens = args.split("--")
            for t in tokens:
                t = t.strip()
                if t.startswith(name + " "):
                    return t[len(name) + 1:].strip().strip('"').strip("'")
            return None
        s_from = get_arg("from")
        s_to   = get_arg("to")
        if not s_from or not s_to:
            print('Thiếu tham số. Ví dụ: python f18_export.py --from "2025-09-01" --to "2025-09-30 23:59:59"')
            sys.exit(1)
        start_dt = parse_dt(s_from)
        end_dt   = parse_dt(s_to)
    else:
        s_from = input("Từ ngày/giờ (YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS): ")
        s_to   = input("Đến ngày/giờ (YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS): ")
        start_dt = parse_dt(s_from)
        end_dt   = parse_dt(s_to)

    if end_dt < start_dt:
        raise ValueError("Khoảng thời gian không hợp lệ: 'đến' < 'từ'.")
    return start_dt, end_dt

def export_csv(rows, out_path):
    if not rows:
        print("Không có bản ghi phù hợp để xuất.")
        return
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Đã lưu CSV: {out_path} ({len(rows)} dòng)")

def main():
    start_dt, end_dt = ask_range()
    print(f"Lấy dữ liệu từ {start_dt} đến {end_dt}")

    try:
        from zk import ZK
    except ImportError:
        print("Chưa cài pyzk. Hãy chạy: pip install pyzk")
        sys.exit(1)

    zk = ZK(
        DEVICE_IP,
        port=DEVICE_PORT,
        timeout=TIMEOUT_S,
        password=COMM_KEY,     # comm-key
        force_udp=False,
        ommit_ping=False
    )

    conn = None
    try:
        print(f"Kết nối {DEVICE_IP}:{DEVICE_PORT} ...")
        conn = zk.connect()

        # Khuyến nghị khóa tạm khi đọc
        try:
            conn.disable_device()
        except Exception:
            pass

        # Thiết bị không filter theo thời gian được; ta kéo hết rồi lọc
        raw_logs = conn.get_attendance() or []
        print(f"Nhận {len(raw_logs)} bản ghi, đang lọc ...")

        rows = []
        for att in raw_logs:
            ts = getattr(att, "timestamp", None)
            if not ts:
                continue
            if start_dt <= ts <= end_dt:
                rows.append({
                    "user_id": getattr(att, "user_id", ""),
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": getattr(att, "status", ""),
                    "punch": getattr(att, "punch", ""),
                    "device_ip": DEVICE_IP
                })

        rows.sort(key=lambda r: (r["user_id"], r["timestamp"]))
        out_name = f"attendance_{start_dt.strftime('%Y%m%d_%H%M%S')}_to_{end_dt.strftime('%Y%m%d_%H%M%S')}.csv"
        export_csv(rows, out_name)

    except Exception as e:
        print(f"Lỗi khi kết nối/đọc dữ liệu: {e}")
    finally:
        if conn:
            try:
                conn.enable_device()
            except Exception:
                pass
            try:
                conn.disconnect()
            except Exception:
                pass

if __name__ == "__main__":
    main()

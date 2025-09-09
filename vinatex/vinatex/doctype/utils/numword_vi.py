import re
from decimal import Decimal, ROUND_HALF_UP

import frappe

DG = ["không","một","hai","ba","bốn","năm","sáu","bảy","tám","chín"]
THOUSANDS = ["", "nghìn", "triệu", "tỷ"]  # lặp theo chu kỳ 4 nhóm
USE_LINH = True  # False nếu bạn muốn dùng "lẻ"

def _read_triplet(n: int, use_linh: bool = USE_LINH) -> str:
    a, b, c = n // 100, (n % 100) // 10, n % 10
    out = []
    if a > 0:
        out += [DG[a], "trăm"]
        if b == 0 and c != 0:
            out.append("linh" if use_linh else "lẻ")

    if b > 1:
        out += [DG[b], "mươi"]
        if c == 1:
            out.append("mốt")
        elif c == 5:
            out.append("lăm")
        elif c != 0:
            out.append(DG[c])
    elif b == 1:
        out += ["mười"]
        if c == 5:
            out.append("lăm")
        elif c != 0:
            out.append(DG[c])
    else:  # b == 0
        if a == 0 and c != 0:
            out.append(DG[c])
        elif c != 0 and a != 0:
            out.append(DG[c])

    return " ".join(out).strip()

def _int_to_words(n: int, use_linh: bool = USE_LINH) -> str:
    if n == 0:
        return "không"
    parts = []
    idx = 0
    while n > 0:
        trip = n % 1000
        if trip:
            block = _read_triplet(trip, use_linh)
            unit = THOUSANDS[idx % 4]  # "", nghìn, triệu, tỷ (rồi lặp)
            if block:
                parts.append(block + ((" " + unit) if unit else ""))
        n //= 1000
        idx += 1
    return " ".join(reversed(parts)).strip()

def number_to_words(number, currency):
    """
    Trả về chuỗi như: "Một trăm hai mươi ba nghìn ... đồng [và ... xu]"
    - Đơn vị, đơn vị lẻ lấy từ DocType Currency:
      + currency_vietnamese (ví dụ: "đồng")
      + fraction_vietnamese (ví dụ: "và")
      + fraction_units_vietnamese (ví dụ: "xu")
    - Làm tròn 2 chữ số phần lẻ (chuẩn tiền tệ). Nếu carry thành 100 xu -> cộng 1 đồng.
    """
    # ---- Lấy cấu hình đơn vị từ Currency
    currency_vietnamese = frappe.get_value("Currency", currency, "custom_currency_vietnamese") or "đồng"
    fraction_vn = frappe.get_value("Currency", currency, "custom_fraction_vietnamese") or "và"
    fraction_unit_vn = frappe.get_value("Currency", currency, "custom_fraction_units_vietnamese") or "xu"

    # ---- Chuẩn hoá số bằng Decimal (không dùng float)
    try:
        d = Decimal(str(number))
    except Exception:
        return "Không phải số hợp lệ"

    neg = d < 0
    d = abs(d)

    # Mặc định làm tròn 2 chữ số cho tiền tệ
    d_rounded = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Tách phần nguyên & lẻ (xu)
    int_part = int(d_rounded)  # đơn vị tiền
    frac_part = int((d_rounded - Decimal(int_part)) * 100)  # 0..99 xu

    # Trường hợp làm tròn đẩy lên 100 xu
    if frac_part == 100:
        int_part += 1
        frac_part = 0

    words_int = _int_to_words(int_part, use_linh=USE_LINH)

    # Ghép chuỗi kết quả
    result = ""
    if neg:
        result += "âm "

    result += words_int + f" {currency_vietnamese}"

    if frac_part > 0:
        # đọc 2 chữ số xu bằng _read_triplet trên chuỗi 2 số
        xu_words = _read_triplet(frac_part)
        result += f" {fraction_vn} {xu_words} {fraction_unit_vn}"
    else:
        # không thêm "chẵn" ở đây, nếu muốn thì tuỳ ý:
        # result += " chẵn"
        pass

    result = re.sub(r"\s+", " ", result).strip()
    return result[:1].upper() + result[1:]

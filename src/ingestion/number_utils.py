"""Chuẩn hóa số liệu định dạng Việt Nam (BCTC) từ string thô sang float.

Không phụ thuộc vào bất kỳ module nào khác trong pipeline (module "đáy",
giống models.py) -- table_extractor_native.py, table_extractor_scan.py, và
ExtractedTable.to_normalized_records() (models.py) đều gọi normalize_vn_number()
từ đây, đảm bảo behavior giống hệt nhau dù bảng đến từ nguồn nào.

Các định dạng cần xử lý trong BCTC Việt Nam:
    "1.234.567"        -> 1234567.0   (dấu chấm = phân cách hàng nghìn)
    "1.234.567,89"      -> 1234567.89  (dấu phẩy = phân cách thập phân)
    "(7.717.501.374)"  -> -7717501374.0  (ngoặc đơn = số âm, quy ước kế toán)
    "-7.717.501.374"   -> -7717501374.0  (dấu trừ tường minh)
    "-"                -> None          (ô trống/không có dữ liệu, quy ước BCTC)
    ""                 -> None
    "1,234,567"        -> 1234567.0   (fallback: kiểu Mỹ, dấu phẩy = hàng nghìn,
                                        phòng trường hợp dữ liệu từ nguồn CSV
                                        export theo convention khác)
"""

import re
from typing import Optional


def normalize_vn_number(
    raw: Optional[str], dash_as: Optional[float] = None
) -> Optional[float]:
    """Chuyển 1 ô số liệu dạng string thô (kiểu VN) thành float.

    Args:
        raw: Giá trị thô đọc được từ bảng (PDF native hoặc OCR).
        dash_as: Giá trị trả về khi ô chỉ chứa dấu gạch ngang ("-", "–", "—")
          -- quy ước phổ biến trong BCTC VN nghĩa là "không có số liệu"
          (KHÔNG đồng nghĩa với 0). Mặc định None để phân biệt rõ với ô
          thực sự bằng 0. Đổi thành 0.0 ở nơi gọi nếu pipeline downstream
          cần giá trị số để tính toán (SUM/AVG) mà không muốn xử lý NULL.

    Returns:
        float nếu parse được, None nếu ô rỗng, chỉ có dấu gạch ngang, hoặc
        không parse được thành số (không raise exception -- lỗi format dữ
        liệu không nên làm crash cả pipeline, chỉ nên trả None và để tầng
        gọi tự quyết định log/bỏ qua).
    """
    if raw is None:
        return None

    s = raw.strip()
    if not s:
        return None

    # Chuẩn hóa các biến thể dấu gạch ngang (Unicode en-dash/em-dash cũng
    # hay xuất hiện do OCR hoặc copy-paste từ Excel)
    if s in ("-", "–", "—", "--"):
        return dash_as

    # Số âm kiểu kế toán: (1.234) nghĩa là -1234
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    # Dấu trừ tường minh (có thể đứng trước hoặc sau khi đã bỏ ngoặc)
    if s.startswith("-"):
        negative = True
        s = s[1:].strip()

    # Loại bỏ ký tự không phải số/dấu phân cách (đơn vị "VNĐ", "%", khoảng
    # trắng do OCR chèn nhầm...)
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None

    s = _unify_separators(s)

    try:
        value = float(s)
    except ValueError:
        return None

    return -value if negative else value


def _unify_separators(s: str) -> str:
    """Quy toàn bộ dấu phân cách về chuẩn Python (dấu chấm = thập phân).

    Xử lý cả 2 convention có thể gặp trong dữ liệu BCTC VN:
        - Chuẩn VN: chấm = hàng nghìn, phẩy = thập phân -> "1.234.567,89"
        - Chuẩn Mỹ (một số nguồn CSV export): phẩy = hàng nghìn,
          chấm = thập phân -> "1,234,567.89"
    """
    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        # Ký tự xuất hiện SAU CÙNG trong chuỗi là dấu thập phân thật sự
        # (vì phân cách hàng nghìn luôn lặp lại ở nhóm 3 số, dấu thập phân
        # chỉ xuất hiện đúng 1 lần và ở vị trí cuối)
        if s.rfind(",") > s.rfind("."):
            # Chuẩn VN: "1.234.567,89"
            s = s.replace(".", "").replace(",", ".")
        else:
            # Chuẩn Mỹ: "1,234,567.89"
            s = s.replace(",", "")
        return s

    if has_comma and not has_dot:
        # Chỉ có dấu phẩy: coi là thập phân theo chuẩn VN ("1234567,89")
        # trừ khi có nhiều hơn 1 dấu phẩy -> chắc chắn là hàng nghìn kiểu Mỹ
        if s.count(",") > 1:
            return s.replace(",", "")
        return s.replace(",", ".")

    if has_dot and not has_comma:
        # Chỉ có dấu chấm: mặc định coi là hàng nghìn (convention phổ biến
        # nhất trong BCTC VN, vd "1.234.567"). Trường hợp hiếm ô chỉ có 1
        # dấu chấm với đúng 2 chữ số sau (như "1234.56") sẽ bị hiểu nhầm
        # thành hàng nghìn -- chấp nhận đánh đổi này vì tỷ lệ BCTC VN dùng
        # dấu chấm làm thập phân gần như không có.
        return s.replace(".", "")

    return s


def is_numeric_like(raw: Optional[str]) -> bool:
    """Kiểm tra nhanh 1 ô có khả năng là số hay không (dùng để dò cột số
    theo giá trị, xem ExtractedTable.to_normalized_records() trong
    models.py). Không tính ô rỗng/dấu gạch ngang là "numeric" để tránh
    các cột toàn ô trống bị nhận nhầm là cột số."""
    if raw is None:
        return False
    s = raw.strip()
    if not s or s in ("-", "–", "—", "--"):
        return False
    return normalize_vn_number(raw) is not None

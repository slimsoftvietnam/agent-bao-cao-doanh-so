"""Chuẩn hoá văn bản, số, ngày từ các file Excel "bẩn" (tiếng Việt / tiếng Anh).

Ý tưởng cleanNumber() lấy từ repo tham khảo DEKX-LAB/supermarket-sales-report,
được mở rộng cho định dạng số Việt Nam (1.250.000đ, 12,5) và ngày dd/mm/yyyy.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Any, Optional


def strip_accents(s: Any) -> str:
    s = str(s).replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def norm(s: Any) -> str:
    """Chữ thường, bỏ dấu, bỏ ký tự đặc biệt, gọn khoảng trắng: 'Đơn giá (VNĐ)' -> 'don gia vnd'."""
    if s is None:
        return ""
    t = strip_accents(s).casefold()
    t = re.sub(r"[^a-z0-9\s]", " ", t.replace("_", " "))
    return re.sub(r"\s+", " ", t).strip()


def is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:  # NaN
        return True
    if hasattr(v, "isnull") or type(v).__name__ == "NaTType":
        return True
    return isinstance(v, str) and not v.strip()


_CURRENCY = re.compile(r"(vnđ|vnd|đồng|₫|đ|\$|usd)", re.I)


def parse_number(v: Any) -> Optional[float]:
    """'1.250.000đ' -> 1250000, '1,250.50' -> 1250.5, '12,5' -> 12.5, '(500)' -> -500. Không đọc được -> None."""
    if is_blank(v) or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) or type(v).__module__ == "numpy":
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if f != f else f
    s = str(v).strip().lower()
    neg = s.startswith("(") and s.endswith(")")
    s = _CURRENCY.sub("", s).replace(" ", "").replace(" ", "").strip("()")
    if s.startswith("-"):
        neg = True
    if any(ch.isalpha() for ch in s):
        return None
    s = re.sub(r"[^\d.,]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        if len(parts) > 2:
            s = s.replace(sep, "")
        elif len(parts[1]) == 3 and parts[0] not in ("", "0"):
            s = parts[0] + parts[1]  # 1.250 -> 1250 (dấu chấm ngăn cách hàng nghìn)
        else:
            s = (parts[0] or "0") + "." + parts[1]
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_DMY = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})")


def parse_date(v: Any) -> Optional[dt.date]:
    """Datetime, số serial Excel, 'dd/mm/yyyy', 'dd-mm-yyyy', 'yyyy-mm-dd'. Ngày đứng trước tháng (chuẩn VN)."""
    if is_blank(v):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < float(v) < 80000:
            return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(v))).date()
        return None
    s = str(v).strip()
    try:
        m = _ISO.match(s)
        if m:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        m = _DMY.match(s)
        if m:
            y = int(m[3])
            y += 2000 if y < 100 else 0
            return dt.date(y, int(m[2]), int(m[1]))
    except ValueError:
        return None
    return None


def fmt_vnd(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".") + " ₫"


def fmt_short(x: float) -> str:
    """Rút gọn: 35.200.000 -> '35,2 tr'; 1.250.000.000 -> '1,25 tỷ'."""
    a = abs(x)
    if a >= 1e9:
        return f"{x / 1e9:.2f}".replace(".", ",") + " tỷ"
    if a >= 1e6:
        return f"{x / 1e6:.1f}".replace(".", ",") + " tr"
    if a >= 1e3:
        return f"{x / 1e3:.0f}k"
    return f"{x:.0f}"


def fmt_pct(x: Optional[float], sign: bool = False) -> str:
    if x is None:
        return "n/a"
    s = f"{x:+.1f}" if sign else f"{x:.1f}"
    return s.replace(".", ",") + "%"

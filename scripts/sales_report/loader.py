"""Đọc, nhận diện cột và gộp dữ liệu từ nhiều file Excel/CSV có cấu trúc khác nhau."""
from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from .parsing import is_blank, norm, parse_date, parse_number, strip_accents

DATA_EXT = {".xlsx", ".xlsm", ".xls", ".csv"}
SUMMARY_WORDS = ("tong", "total", "cong", "sum", "grand")
FIELDS = ("date", "product", "quantity", "unit_price", "revenue", "seller", "sku")
NUMERIC = ("quantity", "unit_price", "revenue")
COLS = ["date", "product", "quantity", "unit_price", "revenue", "seller", "source_id", "file", "row"]


@dataclass
class FileResult:
    path: Path
    source_id: Optional[str] = None
    sha256: str = ""
    df: Optional[pd.DataFrame] = None
    fatal: Optional[str] = None            # file hỏng / không đọc được
    structure_error: Optional[str] = None  # đọc được nhưng thiếu cột bắt buộc
    headers_seen: list = field(default_factory=list)
    sheets_used: list = field(default_factory=list)
    sheets_skipped: list = field(default_factory=list)
    column_map: dict = field(default_factory=dict)  # tên cột gốc -> trường chuẩn
    raw_rows: int = 0
    summary_rows: int = 0
    blank_rows: int = 0
    invalid_date_rows: int = 0
    missing_value_rows: int = 0
    mismatch_rows: int = 0
    negative_rows: int = 0
    unparseable: dict = field(default_factory=dict)  # trường -> số ô không đọc được
    samples: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def n_rows(self) -> int:
        return 0 if self.df is None else len(self.df)

    @property
    def content_hash(self) -> str:
        """Băng nội dung dữ liệu (không phụ thuộc định dạng file) để bắt file trùng đã đổi tên/định dạng."""
        if self.df is None or self.df.empty:
            return ""
        d = self.df[["date", "product", "quantity", "revenue"]].astype(str)
        rows = sorted("|".join(map(str, r)) for r in d.itertuples(index=False))
        return hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()


def _norm_filename(name: str) -> str:
    """Bỏ dấu, chữ thường, mọi ký tự lạ -> '_', giữ ký tự đại diện * ?"""
    return re.sub(r"[^a-z0-9*?]+", "_", strip_accents(name).casefold()).strip("_")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def discover(inbox: Path, sources: list[dict]) -> tuple[dict[str, list[Path]], list[Path]]:
    """Ghép file trong inbox vào từng nguồn theo file_patterns. Trả (nguồn -> file, file không khớp nguồn nào)."""
    files = sorted(p for p in inbox.iterdir()
                   if p.is_file() and p.suffix.lower() in DATA_EXT and not p.name.startswith(("~$", ".")))
    matched: dict[str, list[Path]] = {s["id"]: [] for s in sources}
    used: set[Path] = set()
    for s in sources:
        pats = [_norm_filename(p) for p in s["file_patterns"]]
        for p in files:
            if any(fnmatch.fnmatchcase(_norm_filename(p.stem), pat) for pat in pats):
                matched[s["id"]].append(p)
                used.add(p)
    return matched, [p for p in files if p not in used]


def _alias_map(columns_cfg: dict) -> dict[str, list[str]]:
    return {f: [norm(a) for a in aliases] for f, aliases in columns_cfg.items()}


def map_headers(cells: list, aliases: dict[str, list[str]]) -> dict[int, str]:
    """cột -> trường chuẩn. Lượt 1: khớp nguyên văn; lượt 2: tiêu đề có chứa từ đồng nghĩa (ưu tiên từ dài nhất)."""
    heads = [norm(c) if not is_blank(c) else "" for c in cells]
    mapping: dict[int, str] = {}
    taken: set[str] = set()
    for i, h in enumerate(heads):
        if not h:
            continue
        for f, al in aliases.items():
            if f not in taken and h in al:
                mapping[i] = f
                taken.add(f)
                break
    for i, h in enumerate(heads):
        if not h or i in mapping:
            continue
        best, best_len = None, 0
        for f, al in aliases.items():
            if f in taken:
                continue
            for a in al:
                if len(a) >= 3 and f" {a} " in f" {h} " and len(a) > best_len:
                    best, best_len = f, len(a)
        if best:
            mapping[i] = best
            taken.add(best)
    return mapping


def _read_raw(path: Path) -> dict[str, pd.DataFrame]:
    if path.suffix.lower() == ".csv":
        last = None
        for enc in ("utf-8-sig", "utf-8", "cp1258", "cp1252"):
            try:
                return {"csv": pd.read_csv(path, header=None, dtype=object, encoding=enc,
                                           skip_blank_lines=False, engine="python")}
            except UnicodeDecodeError as e:
                last = e
            except pd.errors.EmptyDataError:
                return {"csv": pd.DataFrame()}
        raise last  # type: ignore[misc]
    return pd.read_excel(path, sheet_name=None, header=None, dtype=object)


def _find_header(df: pd.DataFrame, aliases: dict, scan: int = 30, min_score: int = 3):
    best_score, best_i, best_map = 0, None, {}
    for i in range(min(scan, len(df))):
        m = map_headers(list(df.iloc[i]), aliases)
        score = len({f for f in m.values() if f != "sku"})
        if score > best_score:
            best_score, best_i, best_map = score, i, m
    return (best_i, best_map) if best_score >= min_score else (None, {})


def load_file(path: Path, source: Optional[dict], columns_cfg: dict,
              required: tuple[str, ...] = ("date", "product")) -> FileResult:
    res = FileResult(path=path, source_id=source["id"] if source else None, sha256=sha256_of(path))
    aliases = _alias_map(columns_cfg)
    try:
        sheets = _read_raw(path)
    except Exception as e:  # file hỏng, sai định dạng, có mật khẩu...
        res.fatal = f"{type(e).__name__}: {str(e)[:160]}"
        return res

    owner = source["owner"] if source else path.stem
    rows_out: list[dict] = []
    only = [norm(x) for x in (source or {}).get("sheets", [])]
    for sheet_name, raw in sheets.items():
        if only and norm(sheet_name) not in only:
            res.sheets_skipped.append(f"{sheet_name} (không nằm trong danh sách tab của nguồn)")
            continue
        if raw is None or raw.empty:
            res.sheets_skipped.append(f"{sheet_name} (trống)")
            continue
        hi, cmap = _find_header(raw, aliases)
        if hi is None:
            res.sheets_skipped.append(f"{sheet_name} (không có bảng dữ liệu)")
            if not res.headers_seen:
                for i in range(min(5, len(raw))):
                    res.headers_seen = [str(c) for c in raw.iloc[i] if not is_blank(c)][:10] or res.headers_seen
            continue
        fields_found = set(cmap.values())
        has_money = "revenue" in fields_found or {"quantity", "unit_price"} <= fields_found
        missing = [f for f in required if f not in fields_found]
        if not has_money:
            missing.append("revenue (hoặc quantity + unit_price)")
        res.headers_seen = [str(c) for c in raw.iloc[hi] if not is_blank(c)]
        if missing:
            res.structure_error = f"Sheet '{sheet_name}' thiếu cột: {', '.join(missing)}"
            res.sheets_skipped.append(f"{sheet_name} (thiếu cột)")
            continue
        res.structure_error = None
        res.sheets_used.append(str(sheet_name))
        for ci, f in cmap.items():
            res.column_map[str(raw.iloc[hi, ci])] = f
        body = raw.iloc[hi + 1:]
        res.raw_rows += len(body)
        rows_out += _extract_rows(body, cmap, res, owner, path.name)

    if res.sheets_used:
        res.structure_error = None
        res.df = pd.DataFrame(rows_out, columns=COLS)
        res.df["source_id"] = res.source_id
    elif not res.structure_error and not res.fatal:
        res.structure_error = ("Không tìm thấy bảng dữ liệu (cần tối thiểu 3 cột nhận diện được như "
                               "ngày, sản phẩm, doanh thu/số lượng/đơn giá)")
    return res


def _extract_rows(body: pd.DataFrame, cmap: dict, res: FileResult, owner: str, fname: str) -> list[dict]:
    out = []
    inv = {f: i for i, f in cmap.items()}

    def cell(row, f):
        i = inv.get(f)
        return None if i is None else row.iloc[i]

    for idx, row in body.iterrows():
        if all(is_blank(v) for v in row):
            res.blank_rows += 1
            continue
        xl_row = int(idx) + 1
        raw_date, raw_prod = cell(row, "date"), cell(row, "product")
        d, prod = parse_date(raw_date), (None if is_blank(raw_prod) else str(raw_prod).strip())
        label = norm(raw_prod) if prod else (norm(raw_date) if not is_blank(raw_date) else "")
        rev_raw = cell(row, "revenue")
        if label.startswith(SUMMARY_WORDS) or (d is None and prod is None and not is_blank(rev_raw)):
            res.summary_rows += 1
            continue
        vals = {}
        for f in NUMERIC:
            raw = cell(row, f)
            vals[f] = parse_number(raw)
            if vals[f] is None and not is_blank(raw):
                res.unparseable[f] = res.unparseable.get(f, 0) + 1
                if len(res.samples) < 5:
                    res.samples.append(f"{fname} dòng {xl_row}: '{raw}' không đọc được (cột {f})")
        if d is None:
            res.invalid_date_rows += 1
            if not is_blank(raw_date):
                res.unparseable["date"] = res.unparseable.get("date", 0) + 1
                if len(res.samples) < 5:
                    res.samples.append(f"{fname} dòng {xl_row}: ngày '{raw_date}' không đọc được")
            continue
        q, p, rev = vals["quantity"], vals["unit_price"], vals["revenue"]
        if rev is None and q is not None and p is not None:
            rev = q * p
        if rev is None:
            res.missing_value_rows += 1
        elif q is not None and p is not None and abs(rev - q * p) > max(1.0, 0.01 * abs(rev)):
            res.mismatch_rows += 1
        if (rev is not None and rev < 0) or (q is not None and q < 0):
            res.negative_rows += 1
        seller = cell(row, "seller")
        out.append({
            "date": d, "product": prod or "(không tên)", "quantity": q, "unit_price": p, "revenue": rev,
            "seller": owner if is_blank(seller) else str(seller).strip(),
            "source_id": res.source_id, "file": fname, "row": xl_row,
        })
    return out


@dataclass
class LoadResult:
    files: list[FileResult]
    by_source: dict[str, list[FileResult]]
    unmatched: list[FileResult]
    data: pd.DataFrame


def load_all(inbox: Path, cfg: dict) -> LoadResult:
    sources = cfg["sources"]["sources"]
    columns_cfg = cfg["sources"]["columns"]
    required = tuple((cfg["rules"]["rules"].get("wrong_structure") or {}).get("required_fields", ["date", "product"]))
    matched, unmatched = discover(inbox, sources)
    by_source: dict[str, list[FileResult]] = {}
    files: list[FileResult] = []
    for s in sources:
        by_source[s["id"]] = [load_file(p, s, columns_cfg, required) for p in matched[s["id"]]]
        files += by_source[s["id"]]
    un = [load_file(p, None, columns_cfg, required) for p in unmatched]
    frames = [f.df for f in files if f.df is not None and not f.df.empty]
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)
    return LoadResult(files=files, by_source=by_source, unmatched=un, data=data)

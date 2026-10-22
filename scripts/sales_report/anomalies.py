"""Phát hiện bất thường trong dữ liệu đầu vào. Mọi ngưỡng đọc từ config/alert_rules.yaml."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import asdict, dataclass

from .config import rule
from .loader import LoadResult
from .metrics import baseline, period_bounds, period_series, prepare
from .parsing import fmt_pct, fmt_short

CRITICAL, WARNING, INFO = "critical", "warning", "info"


@dataclass
class Issue:
    code: str
    severity: str
    title: str
    detail: str
    action: str
    source_id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _mk(cfg, code, title, detail, action, source_id="", severity=None):
    r = rule(cfg, code)
    if not r["enabled"]:
        return None
    return Issue(code, severity or r["severity"], title, detail, action, source_id)



def detect(load: LoadResult, cfg: dict, rd: dt.date, kind: str = "day") -> tuple[list[Issue], dict]:
    issues: list[Issue] = []
    start, _ = period_bounds(rd, kind)
    noun = "ngày" if kind == "day" else "tuần"
    when = f"{rd:%d/%m/%Y}" if kind == "day" else f"{start:%d/%m}–{rd:%d/%m/%Y}"
    sources = {s["id"]: s for s in cfg["sources"]["sources"]}
    owners = [s["owner"] for s in sources.values()]

    def add(i):
        if i:
            issues.append(i)

    # 1. Thiếu file / trùng file / file hỏng / sai cấu trúc / rỗng — theo từng nguồn
    for sid, s in sources.items():
        files = load.by_source.get(sid, [])
        if not files:
            add(_mk(cfg, "missing_file", f"Thiếu file của {s['owner']}",
                    f"Không có file nào khớp mẫu {s['file_patterns']} trong thư mục dữ liệu.",
                    f"Nhắc {s['owner']} tải file doanh số lên Drive đúng thư mục/tên quy ước.", sid))
            continue
        if len(files) > 1:
            same = len({f.sha256 for f in files}) == 1
            add(_mk(cfg, "duplicate_file", f"File của {s['owner']} bị trùng ({len(files)} file)",
                    ("Các file giống hệt nhau: " if same else "Có nhiều file khác nhau cho cùng một nguồn: ")
                    + ", ".join(f.name for f in files),
                    "Giữ lại 1 file đúng, xoá hoặc chuyển phần còn lại sang thư mục lưu trữ.", sid))
        for f in files:
            if f.fatal:
                add(_mk(cfg, "wrong_structure", f"Không đọc được file {f.name}", f.fatal,
                        "Mở file kiểm tra có bị hỏng, đặt mật khẩu hoặc sai định dạng không.", sid))
            elif f.structure_error:
                add(_mk(cfg, "wrong_structure", f"Sai cấu trúc file {f.name}",
                        f"{f.structure_error}. Tiêu đề đọc được: {', '.join(f.headers_seen[:8]) or '(không có)'}.",
                        f"Yêu cầu {s['owner']} dùng đúng cột (Ngày, Sản phẩm, Số lượng, Đơn giá, Thành tiền) "
                        "hoặc bổ sung tên cột mới vào config/sources.yaml.", sid))
            elif f.n_rows == 0:
                add(_mk(cfg, "empty_file", f"File {f.name} không có dòng dữ liệu nào",
                        f"Đọc được {f.raw_rows} dòng thô nhưng không có dòng giao dịch hợp lệ.",
                        f"Hỏi {s['owner']} đã nhập doanh số chưa.", sid))
            else:
                _row_quality(f, s, cfg, rd, add, start, when)
        ok_files = [f for f in files if f.df is not None and f.n_rows > 0]
        if ok_files and not any(((f.df["date"] >= start) & (f.df["date"] <= rd)).any() for f in ok_files) \
                and not s.get("allow_empty_day", False):
            add(_mk(cfg, "no_data_for_date", f"{s['owner']} chưa có doanh số {noun} {when}",
                    f"File {ok_files[0].name} có {sum(f.n_rows for f in ok_files)} dòng nhưng không dòng nào thuộc kỳ báo cáo.",
                    f"Nhắc {s['owner']} cập nhật file; nếu kỳ này thật sự không bán, đặt allow_empty_day: true cho nguồn.", sid))

    # 2. File thừa trong thư mục + trùng nội dung chéo nguồn
    by_hash = defaultdict(list)
    for f in load.files + load.unmatched:
        by_hash[f.sha256].append(f)
    for fs in by_hash.values():
        if len(fs) > 1 and len({f.source_id for f in fs}) > 1:
            add(_mk(cfg, "duplicate_file", "Cùng một file xuất hiện ở nhiều nguồn",
                    "Trùng byte-by-byte: " + ", ".join(f.name for f in fs),
                    "Kiểm tra có ai tải nhầm file của người khác không."))
    by_content = defaultdict(list)
    for f in load.files:
        if f.content_hash:
            by_content[f.content_hash].append(f)
    for fs in by_content.values():
        if len({f.sha256 for f in fs}) > 1 and len({f.source_id for f in fs}) > 1:
            add(_mk(cfg, "duplicate_file", "Hai nguồn có dữ liệu giống hệt nhau",
                    "Cùng nội dung dữ liệu dù file khác nhau: " + ", ".join(f.name for f in fs),
                    "Có thể một người sao chép file của người kia — xác minh trước khi gửi báo cáo."))
    for f in load.unmatched:
        add(_mk(cfg, "unexpected_file", f"File lạ không thuộc nguồn nào: {f.name}",
                "Tên file không khớp file_patterns của bất kỳ nguồn nào, nên bị bỏ qua khi tính.",
                "Đổi tên đúng quy ước hoặc thêm nguồn mới vào config/sources.yaml."))

    # 3. Doanh thu lệch quá ngưỡng
    dev = {"total": None, "sellers": {}}
    r = rule(cfg, "revenue_deviation")
    if r["enabled"] and not load.data.empty:
        d = prepare(load.data, owners)
        thr = float(r.get("threshold_pct", 50))
        scopes = r.get("scope", ["total", "seller"])
        targets = []
        if "total" in scopes:
            targets.append(("Tổng doanh thu", None))
        if "seller" in scopes:
            targets += [(n, n) for n in sorted(set(d["seller"]))]
        for label, seller in targets:
            series = period_series(d, rd, kind, seller)
            base, desc = baseline(series, rd, r, kind)
            cur = float(series.get(rd, 0.0))
            if base is None or base < float(r.get("min_baseline_revenue", 0)):
                continue
            pct = (cur - base) / base * 100
            rec = {"label": label, "current": cur, "baseline": base, "pct": pct, "desc": desc}
            if seller is None:
                dev["total"] = rec
            else:
                dev["sellers"][label] = rec
            if abs(pct) > thr:
                add(_mk(cfg, "revenue_deviation",
                        f"{label}: doanh thu {noun} {when} lệch {fmt_pct(pct, True)} so với mốc",
                        f"Hôm báo cáo {fmt_short(cur)} vs mốc {fmt_short(base)} ({desc}); ngưỡng ±{thr:.0f}%.",
                        "Xác minh số liệu (nhập thừa/thiếu số 0, thiếu dòng, đơn lớn bất thường) trước khi phát hành.",
                        seller or ""))
    return issues, dev


def _row_quality(f, s, cfg, rd, add, start, when):
    total = f.n_rows + f.missing_value_rows + f.invalid_date_rows
    bad = f.missing_value_rows + f.invalid_date_rows
    if bad:
        r = rule(cfg, "missing_values")
        ratio = bad / max(total, 1)
        sev = r["severity"] if ratio > float(r.get("max_ratio", 0.1)) else WARNING
        detail = (f"{bad}/{total} dòng thiếu/không đọc được (ngày không hợp lệ: {f.invalid_date_rows}, "
                  f"thiếu doanh thu: {f.missing_value_rows}). " + " | ".join(f.samples[:3]))
        add(_mk(cfg, "missing_values", f"{f.name}: {ratio:.0%} dòng có dữ liệu trống/lỗi", detail,
                f"Nhờ {s['owner']} bổ sung các ô trống.", s["id"], severity=sev))
    if f.mismatch_rows:
        add(_mk(cfg, "revenue_mismatch", f"{f.name}: {f.mismatch_rows} dòng Thành tiền ≠ Số lượng × Đơn giá",
                "Chênh lệch vượt dung sai 1%.", "Kiểm tra công thức/số nhập tay.", s["id"]))
    if f.negative_rows:
        add(_mk(cfg, "negative_values", f"{f.name}: {f.negative_rows} dòng có giá trị âm",
                "Có thể là hàng trả lại hoặc nhập sai dấu.", "Xác nhận các dòng trả hàng.", s["id"]))
    d = f.df
    dup = d[(d["date"] >= start) & (d["date"] <= rd)].duplicated(subset=["date", "product", "quantity", "unit_price", "revenue"], keep=False)
    if dup.any():
        add(_mk(cfg, "duplicate_rows", f"{f.name}: {int(dup.sum())} dòng kỳ {when} trùng hệt nhau",
                "Có thể nhập đúp một đơn (hoặc hai đơn giống nhau thật).", "Xác nhận với người nhập.", s["id"]))
    fut = d[d["date"] > rd]
    if len(fut):
        add(_mk(cfg, "future_dates", f"{f.name}: {len(fut)} dòng có ngày sau ngày báo cáo",
                f"Ví dụ ngày {fut['date'].max():%d/%m/%Y}; các dòng này bị bỏ qua.", "Kiểm tra gõ nhầm ngày/tháng.", s["id"]))


def summarize(issues: list[Issue]) -> dict:
    crit = [i for i in issues if i.severity == CRITICAL]
    warn = [i for i in issues if i.severity == WARNING]
    return {"status": "anomaly" if crit else ("ok_with_warnings" if warn else "ok"),
            "critical": len(crit), "warnings": len(warn)}

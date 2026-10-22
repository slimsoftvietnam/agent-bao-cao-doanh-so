#!/usr/bin/env python3
"""Thiết lập lần đầu: kiểm tra file Excel người dùng đưa vào, ghi cấu hình, tạo thông tin lịch chạy.

  python scripts/onboard.py status                       # đã cấu hình chưa?
  python scripts/onboard.py inspect <file|thư mục> ...   # phân tích cấu trúc từng file (JSON)
  python scripts/onboard.py write-config answers.json    # ghi config/*.yaml + config/schedule.yaml
  python scripts/onboard.py collect --out inbox          # chép file cục bộ (local_path) vào inbox để chạy ngay
  python scripts/onboard.py make-workflow                # tạo .github/workflows/bao-cao-doanh-so.yml (lịch chạy GitHub Actions, không cần agent)

Cấu trúc answers.json: xem docs/HUONG-DAN-SU-DUNG.md (mục "Thiết lập") hoặc references/answers.example.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sales_report.loader import DATA_EXT, load_file  # noqa: E402
from sales_report.parsing import strip_accents  # noqa: E402

SKILL = HERE.parent
CONFIG = Path(os.environ.get("BCDS_CONFIG_DIR") or SKILL / "config")  # đổi thư mục config khi kiểm thử
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAYS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
PLACEHOLDER = ("example.com", "DAN_FOLDER_ID", "DAN_SPREADSHEET_ID")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", strip_accents(text).lower()).strip("_") or "nguoi"


def drive_id(url: str) -> tuple[str, str]:
    """-> (loại, id): folder | file | sheet. Loại rỗng nếu không nhận ra."""
    for kind, pat in (("folder", r"/folders/([\w-]+)"), ("sheet", r"/spreadsheets/d/([\w-]+)"),
                      ("file", r"/file/d/([\w-]+)"), ("file", r"[?&]id=([\w-]+)")):
        m = re.search(pat, url or "")
        if m:
            return kind, m.group(1)
    return "", ""


def file_pattern(name: str) -> str:
    """'Doanh_so_An_T10.xlsx' -> 'Doanh_so_An*' (bỏ đuôi tháng/năm/số thứ tự để lần sau file mới vẫn khớp)."""
    stem = Path(name).stem
    stem = re.sub(r"(?:[_\-\s]*(?:t\d{1,2}|20\d\d|\d{1,2}|thang\d*|oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep|\(\d+\)))+$", "", stem, flags=re.I)
    return (stem or Path(name).stem) + "*"


def load_yaml(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dump_yaml(name: str, data: dict, header: str = "") -> None:
    with open(CONFIG / name, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=110, default_flow_style=False)


# ---------------------------------------------------------------- status
def cmd_status(_a) -> int:
    marker = CONFIG / ".configured"
    text = "".join((CONFIG / n).read_text(encoding="utf-8") for n in ("sources.yaml", "recipients.yaml") if (CONFIG / n).exists())
    holders = [p for p in PLACEHOLDER if p in text]
    st = {"configured": marker.exists() and not holders, "marker": marker.exists(), "placeholders_left": holders}
    if marker.exists():
        st["info"] = json.loads(marker.read_text(encoding="utf-8"))
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- inspect
def cmd_inspect(a) -> int:
    cols = load_yaml("sources.yaml")["columns"]
    paths: list[Path] = []
    for x in a.paths:
        p = Path(x)
        paths += sorted(q for q in p.iterdir() if q.suffix.lower() in DATA_EXT and not q.name.startswith(("~$", "."))) if p.is_dir() else [p]
    out = []
    for p in paths:
        r = load_file(p, None, cols)
        item = {"path": str(p), "name": p.name, "readable": r.fatal is None, "pattern": file_pattern(p.name)}
        if r.fatal:
            item["error"] = r.fatal
        elif r.df is None or r.df.empty:
            item.update(ok=False, problem=r.structure_error or "Không có dòng giao dịch nào",
                        headers_seen=r.headers_seen, sheets_skipped=r.sheets_skipped)
        else:
            df = r.df
            sellers = [s for s, _ in sorted(df["seller"].value_counts().items(), key=lambda kv: -kv[1])]
            noise = {"doanh", "so", "doanhso", "sales", "bao", "cao", "baocao", "report", "thang", "oct", "nov", "dec", "jan", "feb",
                     "mar", "apr", "may", "jun", "jul", "aug", "sep"}
            toks = [t for t in re.split(r"[_\-\s]+", strip_accents(p.stem).lower()) if t and t not in noise and not re.fullmatch(r"t?\d+", t)]
            guess = " ".join(toks).title()
            item.update(ok=True, rows=int(len(df)), date_from=str(df["date"].min()), date_to=str(df["date"].max()),
                        revenue_total=float(df["revenue"].fillna(0).sum()), sheets_used=r.sheets_used,
                        columns_detected=r.column_map, seller_values=sellers[:5],
                        owner_suggestion=sellers[0] if r.column_map and "seller" in r.column_map.values() and sellers else guess,
                        has_seller_column="seller" in r.column_map.values(),
                        warnings=[w for w in (
                            f"{r.missing_value_rows} dòng thiếu doanh thu" if r.missing_value_rows else "",
                            f"{r.invalid_date_rows} dòng ngày không hợp lệ" if r.invalid_date_rows else "",
                            f"{r.mismatch_rows} dòng Thành tiền ≠ SL × Đơn giá" if r.mismatch_rows else "") if w])
        out.append(item)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- write-config
def cron_for(freq: str, weekday: str, time: str, tz: str, days: list[str]) -> dict:
    hh, mm = (int(x) for x in time.split(":"))
    try:
        from zoneinfo import ZoneInfo
        off = dt.datetime.now(ZoneInfo(tz)).utcoffset() or dt.timedelta(0)
    except Exception:
        off = dt.timedelta(hours=7)
    mins = hh * 60 + mm - int(off.total_seconds() // 60)
    shift = 0
    if mins < 0:
        mins, shift = mins + 1440, -1
    elif mins >= 1440:
        mins, shift = mins - 1440, 1
    sel = [weekday] if freq == "weekly" else days
    idx = sorted({(WEEKDAYS.index(d) + shift) % 7 for d in sel})
    cron = lambda h, m, ds: f"{m} {h} * * " + ",".join(str((i + 1) % 7) for i in ds)  # cron: 0=CN, 1=T2
    return {"local": cron(hh, mm, [WEEKDAYS.index(d) for d in sel]), "utc": cron(mins // 60, mins % 60, idx)}


def cmd_write_config(a) -> int:
    ans = json.loads(Path(a.answers).read_text(encoding="utf-8"))
    src_cfg = load_yaml("sources.yaml")
    freq = "weekly" if ans.get("frequency", "daily") in ("weekly", "week") else "daily"
    tz = ans.get("timezone", "Asia/Ho_Chi_Minh")
    when = ans.get("time", "08:00")
    weekday = ans.get("weekday", "monday")
    days = ans.get("days") or ["monday", "tuesday", "wednesday", "thursday", "friday"]
    if weekday not in WEEKDAYS or any(d not in WEEKDAYS for d in days):
        raise SystemExit("weekday/days phải là monday … sunday")

    general = src_cfg.get("general", {})
    general.update(brand=ans.get("brand") or general.get("brand", "Báo cáo doanh số"), timezone=tz, frequency=freq)
    src_cfg["general"] = general

    sources, seen = [], set()
    for s in ans["sources"]:
        sid = slug(s["owner"])
        while sid in seen:
            sid += "_2"
        seen.add(sid)
        entry = {"id": sid, "owner": s["owner"], "monthly_target": s.get("monthly_target")}
        kind, did = drive_id(s.get("drive_url", ""))
        name = Path(s["local_path"]).name if s.get("local_path") else s.get("file_name", "")
        if kind == "sheet":
            entry["type"] = "gsheet"
            entry["gsheet"] = {"spreadsheet_id": did, "sheet_name": s.get("sheet_name", "")}
            entry["file_patterns"] = [f"{sid}*"]
        else:
            entry["type"] = "file"
            entry["drive"] = {("folder_id" if kind == "folder" else "file_id"): did} if did else {}
            if name:
                entry["drive"]["name_contains"] = file_pattern(name).rstrip("*")
            entry["file_patterns"] = [file_pattern(name)] if name else [f"{sid}*"]
        if s.get("local_path"):
            entry["local_path"] = s["local_path"]
        entry["allow_empty_day"] = bool(s.get("allow_empty_day", False))
        sources.append(entry)
    src_cfg["sources"] = sources
    dump_yaml("sources.yaml", src_cfg, "# Tạo bởi scripts/onboard.py — sửa tay thoải mái. Giải thích các trường: docs/HUONG-DAN-SU-DUNG.md\n")

    team = [x for x in ans["report_email"]]
    owner_email = ans.get("owner_email") or team[0]
    rec = {
        "owner": {"name": ans.get("owner_name", "Người phụ trách"), "email": owner_email,
                  "zalo": {"target": ans.get("zalo_owner", "")}},
        "team": {"to": team, "cc": ans.get("cc", []), "zalo_group": ans.get("zalo_group", "")},
        "email": {"subject_prefix": ans.get("subject_prefix", "[Báo cáo doanh số]")},
        "zalo_queue": {"enabled": bool(ans.get("zalo_queue_sheet_url")), "spreadsheet_id": drive_id(ans.get("zalo_queue_sheet_url", ""))[1],
                       "sheet_name": "ZaloQueue"},
        "audit_log": {"enabled": bool(ans.get("audit_sheet_url")), "spreadsheet_id": drive_id(ans.get("audit_sheet_url", ""))[1],
                      "sheet_name": "Reports"},
    }
    dump_yaml("recipients.yaml", rec, "# Người nhận. owner = người duy nhất nhận cảnh báo khi dữ liệu bất thường.\n")

    cron = cron_for(freq, weekday, when, tz, days)
    period = "báo cáo tuần trước (Thứ Hai–Chủ Nhật)" if freq == "weekly" else "báo cáo ngày làm việc trước đó"
    human = (f"Mỗi {WEEKDAYS_VI[WEEKDAYS.index(weekday)]} lúc {when}" if freq == "weekly"
             else "Mỗi ngày " + ", ".join(WEEKDAYS_VI[WEEKDAYS.index(d)] for d in days) + f" lúc {when}") + f" ({tz}) → {period}"
    sched = {"frequency": freq, "weekday": weekday if freq == "weekly" else None, "days": days if freq == "daily" else None,
             "time": when, "timezone": tz, "cron_local": cron["local"], "cron_utc": cron["utc"], "description": human,
             "routine_prompt": ("Làm theo SKILL.md ở thư mục gốc repo, chế độ chạy theo lịch: mode=live, "
                                f"frequency={freq}. Lấy file nguồn từ Google Drive/Sheets theo config/sources.yaml, chạy scripts/run_report.py, "
                                "gửi email (kèm file HTML + Excel) và Zalo theo result.json; nếu Zalo không gửi được thì ghi vào hàng đợi Zalo "
                                "và bỏ qua; nếu dữ liệu bất thường chỉ gửi cảnh báo riêng cho người phụ trách.")}
    dump_yaml("schedule.yaml", sched, "# Lịch chạy. cron_utc dùng khi nhập cron kiểu UTC cho routine đám mây.\n")
    (CONFIG / ".configured").write_text(json.dumps({"at": dt.datetime.now().isoformat(timespec="seconds"), "frequency": freq,
                                                    "sources": len(sources)}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"written": ["sources.yaml", "recipients.yaml", "schedule.yaml"], "sources": [s["id"] for s in sources],
                      "schedule": human, "cron_utc": cron["utc"]}, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- collect
def cmd_collect(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    got, missing = [], []
    for s in load_yaml("sources.yaml")["sources"]:
        lp = s.get("local_path")
        if lp and Path(lp).exists():
            shutil.copy2(lp, out / Path(lp).name)
            got.append(Path(lp).name)
        else:
            missing.append(s["id"])
    print(json.dumps({"copied": got, "no_local_file": missing}, ensure_ascii=False, indent=2))
    return 0


WORKFLOW = """name: Báo cáo doanh số tự động
# Tạo bởi scripts/onboard.py make-workflow từ config/schedule.yaml. Chạy trên máy chủ GitHub — không cần mở máy, không cần agent.
# Cần repo RIÊNG TƯ (config có email) và secrets: GMAIL_USER, GMAIL_APP_PASSWORD (mật khẩu ứng dụng Gmail).
on:
  schedule:
    - cron: "{cron}"   # {desc}
  workflow_dispatch:
    inputs:
      mode:
        description: "dry-run (không gửi) | test (chỉ người phụ trách) | live"
        default: "dry-run"
permissions:
  contents: write
jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Tải file nguồn, tính, tạo báo cáo, gửi email
        env:
          GMAIL_USER: ${{{{ secrets.GMAIL_USER }}}}
          GMAIL_APP_PASSWORD: ${{{{ secrets.GMAIL_APP_PASSWORD }}}}
        run: python scripts/auto_run.py --mode ${{{{ github.event.inputs.mode || 'live' }}}}
      - name: Lưu hàng đợi Zalo (gửi bù khi người dùng bật máy)
        run: |
          git config user.name "bao-cao-doanh-so-bot"
          git config user.email "bot@users.noreply.github.com"
          git add zalo-queue || true
          git diff --cached --quiet || (git commit -m "Hàng đợi Zalo" && git push)
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: bao-cao-doanh-so
          path: out/
          retention-days: 30
"""


def cmd_make_workflow(_a) -> int:
    sched = load_yaml("schedule.yaml")
    target = SKILL / ".github" / "workflows" / "bao-cao-doanh-so.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(WORKFLOW.format(cron=sched["cron_utc"], desc=sched.get("description", "")), encoding="utf-8")
    print(json.dumps({"written": str(target), "cron_utc": sched["cron_utc"]}, ensure_ascii=False))
    return 0


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("inspect"); p.add_argument("paths", nargs="+"); p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("write-config"); p.add_argument("answers"); p.set_defaults(fn=cmd_write_config)
    sub.add_parser("make-workflow").set_defaults(fn=cmd_make_workflow)
    p = sub.add_parser("collect"); p.add_argument("--out", default=str(SKILL / "inbox")); p.set_defaults(fn=cmd_collect)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

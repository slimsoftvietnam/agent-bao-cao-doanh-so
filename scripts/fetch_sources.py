#!/usr/bin/env python3
"""Tải file nguồn về inbox/ không cần connector: link Google Drive/Sheets chia sẻ "Bất kỳ ai có đường liên kết".

  python scripts/fetch_sources.py --out inbox            # tải theo config/sources.yaml
  python scripts/fetch_sources.py --out inbox --check    # chỉ in URL sẽ tải

Hỗ trợ: drive.file_id (file Excel/CSV), gsheet.spreadsheet_id (+ sheet_name -> xuất CSV).
Không hỗ trợ: folder_id (cần API/connector để liệt kê) và file riêng tư — dùng connector Google Drive của agent.
Nguồn có local_path tồn tại thì chép file cục bộ.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 bao-cao-doanh-so"}


def source_url(s: dict) -> tuple[str, str] | None:
    """-> (url, tên file gợi ý) hoặc None nếu không tải công khai được."""
    if s.get("type") == "gsheet" and (s.get("gsheet") or {}).get("spreadsheet_id"):
        g = s["gsheet"]
        base = f"https://docs.google.com/spreadsheets/d/{g['spreadsheet_id']}"
        if g.get("sheet_name"):
            return f"{base}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(g['sheet_name'])}", f"{s['id']}.csv"
        return f"{base}/export?format=csv", f"{s['id']}.csv"
    fid = (s.get("drive") or {}).get("file_id")
    if fid:
        return f"https://drive.google.com/uc?export=download&id={fid}", ""
    return None


def download(url: str, out: Path, hint: str) -> Path:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
        cd = r.headers.get("Content-Disposition", "")
    if "text/html" in ctype and data[:200].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise RuntimeError("Google trả về trang HTML (file riêng tư hoặc cần đăng nhập) — chia sẻ 'Bất kỳ ai có đường liên kết' hoặc dùng connector")
    name = hint
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    if m:
        name = urllib.parse.unquote(m.group(1))
    name = name or "file.xlsx"
    path = out / re.sub(r'[\\/:*?"<>|]', "_", name)
    path.write_bytes(data)
    return path


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(SKILL / "inbox"))
    ap.add_argument("--config-dir", default=str(SKILL / "config"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    sources = yaml.safe_load(open(Path(a.config_dir) / "sources.yaml", encoding="utf-8"))["sources"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"downloaded": [], "copied": [], "skipped": [], "failed": []}
    for s in sources:
        lp = s.get("local_path")
        if lp and Path(lp).exists() and not a.check:
            shutil.copy2(lp, out / Path(lp).name)
            report["copied"].append({"id": s["id"], "file": Path(lp).name})
            continue
        u = source_url(s)
        if not u:
            report["skipped"].append({"id": s["id"], "reason": "không có link tải công khai (folder_id/riêng tư) — cần connector hoặc local_path"})
            continue
        if a.check:
            report["downloaded"].append({"id": s["id"], "url": u[0]})
            continue
        try:
            report["downloaded"].append({"id": s["id"], "file": download(u[0], out, u[1]).name})
        except Exception as e:  # noqa: BLE001 — báo từng nguồn, không dừng cả lượt
            report["failed"].append({"id": s["id"], "error": str(e)[:200]})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

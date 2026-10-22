#!/usr/bin/env python3
"""Tải file nguồn về inbox/ không cần connector: link Google Drive/Sheets chia sẻ "Bất kỳ ai có đường liên kết".

  python scripts/fetch_sources.py --out inbox            # tải theo config/sources.yaml
  python scripts/fetch_sources.py --out inbox --check    # chỉ in URL sẽ tải

Mỗi Google Sheet = 1 nhân viên; link cố định trong config. Tải cả workbook dạng .xlsx (mọi tab; loader tự chọn tab có bảng,
giới hạn tab bằng `sheets: [tên]` trong nguồn). Có `gsheet.sheet_name` -> chỉ tab đó (CSV); có `gsheet.gid` -> chỉ tab đó.
Cách truy cập (ưu tiên từ trên xuống):
  1. Biến GOOGLE_SERVICE_ACCOUNT_JSON (tài khoản dịch vụ, Sheet/file đã chia sẻ cho email của nó) -> đọc được file RIÊNG TƯ.
  2. Link chia sẻ "Bất kỳ ai có đường liên kết".
Không hỗ trợ: folder_id (cần API/connector để liệt kê) — dùng connector Google Drive của agent hoặc khai file_id từng file.
Nguồn có local_path tồn tại thì chép file cục bộ.
"""
from __future__ import annotations

import argparse
import json
import os
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
        if g.get("gid") not in (None, ""):
            return f"{base}/export?format=csv&gid={g['gid']}", f"{s['id']}.csv"
        return f"{base}/export?format=xlsx", f"{s['id']}.xlsx"
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


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def sa_session():
    """Phiên có quyền của tài khoản dịch vụ, hoặc None nếu không cấu hình / thiếu thư viện."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError:
        return None
    return AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"]))


def download_sa(sess, s: dict, out: Path) -> Path:
    """Đọc file/Sheet riêng tư qua Drive API: Sheet -> xuất xlsx (mọi tab); file Excel/CSV -> tải nguyên bản."""
    if s.get("type") == "gsheet":
        fid = s["gsheet"]["spreadsheet_id"]
        r = sess.get(f"https://www.googleapis.com/drive/v3/files/{fid}/export", params={"mimeType": XLSX})
        name = f"{s['id']}.xlsx"
    else:
        fid = s["drive"]["file_id"]
        meta = sess.get(f"https://www.googleapis.com/drive/v3/files/{fid}", params={"fields": "name"})
        meta.raise_for_status()
        name = meta.json()["name"]
        r = sess.get(f"https://www.googleapis.com/drive/v3/files/{fid}", params={"alt": "media"})
    r.raise_for_status()
    path = out / re.sub(r'[\\/:*?"<>|]', "_", name)
    path.write_bytes(r.content)
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
    sess = None if a.check else sa_session()
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
            if sess is not None:
                report["downloaded"].append({"id": s["id"], "file": download_sa(sess, s, out).name, "via": "service-account"})
                continue
            report["downloaded"].append({"id": s["id"], "file": download(u[0], out, u[1]).name, "via": "public-link"})
        except Exception as e:  # noqa: BLE001 — báo từng nguồn, không dừng cả lượt
            report["failed"].append({"id": s["id"], "error": str(e)[:200]})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

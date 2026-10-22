#!/usr/bin/env python3
"""Ghi kết quả vào Google Sheet tổng hợp (link cố định) bằng tài khoản dịch vụ — dùng khi không có connector Sheets
(Codex, GitHub Actions, cron). Với Claude Code có connector Sheets, agent ghi trực tiếp từ sheet_update.json.

  GOOGLE_SERVICE_ACCOUNT_JSON='{...}' python scripts/sheets_sync.py push out/2026-10-21/sheet_update.json <spreadsheet_id>
  python scripts/sheets_sync.py plan out/2026-10-21/sheet_update.json <spreadsheet_id>     # in các lời gọi API, không gọi mạng

Cần: pip install google-auth requests ; chia sẻ Google Sheet đích (quyền Biên tập) cho email của tài khoản dịch vụ.
Mỗi lần chạy: ghi đè các tab "Tổng quan", "Theo người", "Sản phẩm", "Theo ngày"; nối thêm 1 dòng vào tab "Lịch sử".
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path

BASE = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.readonly"]


def a1(tab: str, rng: str = "A1") -> str:
    """'Tổng quan'!A1 đã mã hoá cho URL."""
    return urllib.parse.quote(f"'{tab}'!{rng}", safe="")


def plan(update: dict, sid: str, existing_tabs: list[str] | None = None, history_empty: bool = True) -> list[dict]:
    """Danh sách lời gọi REST (method, url, body) cần thực hiện — tách riêng để kiểm thử được mà không cần mạng."""
    calls = []
    have = set(existing_tabs or [])
    names = list(update["tabs"]) + list(update["append"])
    missing = [n for n in names if n not in have]
    if missing:
        calls.append({"method": "POST", "url": f"{BASE}/{sid}:batchUpdate",
                      "body": {"requests": [{"addSheet": {"properties": {"title": n}}} for n in missing]}})
    for tab, rows in update["tabs"].items():
        calls.append({"method": "POST", "url": f"{BASE}/{sid}/values/{a1(tab, 'A:ZZ')}:clear", "body": {}})
        calls.append({"method": "PUT", "url": f"{BASE}/{sid}/values/{a1(tab)}?valueInputOption=USER_ENTERED",
                      "body": {"range": f"'{tab}'!A1", "majorDimension": "ROWS", "values": rows}})
    for tab, rows in update["append"].items():
        header = (update.get("headers") or {}).get(tab)
        values = ([header] if header and (tab in missing or history_empty) else []) + rows
        calls.append({"method": "POST",
                      "url": f"{BASE}/{sid}/values/{a1(tab)}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS",
                      "body": {"majorDimension": "ROWS", "values": values}})
    return calls


def session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    return AuthorizedSession(service_account.Credentials.from_service_account_info(info, scopes=SCOPES))


def push(update: dict, sid: str, sess=None) -> list[str]:
    sess = sess or session()
    r = sess.get(f"{BASE}/{sid}?fields=sheets.properties.title")
    r.raise_for_status()
    tabs = [s["properties"]["title"] for s in r.json().get("sheets", [])]
    hist_empty = True
    for tab in update["append"]:
        if tab in tabs:
            v = sess.get(f"{BASE}/{sid}/values/{a1(tab, 'A1:A1')}")
            hist_empty = not (v.ok and v.json().get("values"))
    log = []
    for c in plan(update, sid, tabs, hist_empty):
        resp = sess.request(c["method"], c["url"], json=c["body"])
        resp.raise_for_status()
        log.append(f"{c['method']} {urllib.parse.unquote(c['url'].split('/spreadsheets/')[1])[:80]} -> {resp.status_code}")
    return log


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 4 or sys.argv[1] not in ("push", "plan"):
        print(__doc__)
        return 1
    update = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    sid = sys.argv[3]
    if sys.argv[1] == "plan":
        for c in plan(update, sid):
            print(c["method"], urllib.parse.unquote(c["url"].split("/spreadsheets/")[1])[:100], str(c["body"])[:80])
        return 0
    try:
        for line in push(update, sid):
            print(line)
    except KeyError:
        print("Thiếu GOOGLE_SERVICE_ACCOUNT_JSON", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

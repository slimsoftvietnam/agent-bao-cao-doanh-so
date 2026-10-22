#!/usr/bin/env python3
"""Phương án dự phòng gửi Gmail qua SMTP khi agent không có connector Gmail.

  GMAIL_USER=... GMAIL_APP_PASSWORD=... python scripts/send_mail.py out/2026-10-21/result.json [--check]

Chỉ thực hiện các action gmail trong result.json có "send": true (dry-run => không gửi gì).
--check: chỉ dựng thư và in ra, không kết nối mạng.
"""
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path


def build(action: dict, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, ", ".join(action["to"]), action["subject"]
    if action.get("cc"):
        msg["Cc"] = ", ".join(action["cc"])
    html = Path(action["body_html_file"]).read_text(encoding="utf-8")
    msg.set_content("Vui lòng xem email ở chế độ HTML.")
    msg.add_alternative(html, subtype="html")
    for f in map(Path, action.get("attachments", [])):
        rd = json.loads(f.with_name("result.json").read_text(encoding="utf-8"))["report_date"]
        if f.suffix == ".xlsx":
            msg.add_attachment(f.read_bytes(), maintype="application",
                               subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f.name)
        else:
            msg.add_attachment(f.read_bytes(), maintype="text", subtype="html", filename=f"Bao-cao-doanh-so-{rd}.html")
    return msg


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if not args:
        print(__doc__)
        return 1
    result = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    user, pwd = os.environ.get("GMAIL_USER", ""), os.environ.get("GMAIL_APP_PASSWORD", "")
    todo = [a for a in result["actions"] if a["channel"] == "gmail"]
    for a in todo:
        if not a["send"]:
            print(f"BỎ QUA (mode={result['mode']}): {a['kind']} -> {a['to']}")
            continue
        msg = build(a, user or "me")
        if check:
            print(f"[check] {msg['Subject']} -> {msg['To']} cc={msg['Cc']} ({len(msg.as_bytes())} bytes)")
            continue
        if not (user and pwd):
            print("Thiếu GMAIL_USER / GMAIL_APP_PASSWORD", file=sys.stderr)
            return 1
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pwd)
            s.send_message(msg)
        print(f"ĐÃ GỬI: {msg['Subject']} -> {msg['To']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

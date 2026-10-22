#!/usr/bin/env python3
"""Gửi Gmail qua SMTP, kèm file HTML + Excel. Chạy được ở mọi nơi (Claude Code, Codex, GitHub Actions) vì không cần connector.

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


def send_actions(result_path: str, check: bool = False) -> list[str]:
    """Gửi mọi action gmail có send=true. Trả danh sách dòng nhật ký; ném RuntimeError nếu thiếu thông tin đăng nhập."""
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    user, pwd = os.environ.get("GMAIL_USER", ""), os.environ.get("GMAIL_APP_PASSWORD", "")
    log = []
    for a in (x for x in result["actions"] if x["channel"] == "gmail"):
        if not a["send"]:
            log.append(f"BỎ QUA (mode={result['mode']}): {a['kind']} -> {a['to']}")
            continue
        msg = build(a, user or "me")
        if check:
            log.append(f"[check] {msg['Subject']} -> {msg['To']} cc={msg['Cc']} ({len(msg.as_bytes())} bytes)")
            continue
        if not (user and pwd):
            raise RuntimeError("Thiếu GMAIL_USER / GMAIL_APP_PASSWORD")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pwd)
            s.send_message(msg)
        log.append(f"ĐÃ GỬI: {msg['Subject']} -> {msg['To']}")
    return log


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    try:
        for line in send_actions(args[0], "--check" in sys.argv):
            print(line)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Chạy tự động KHÔNG cần agent/LLM (dùng cho GitHub Actions hoặc cron): tải file → tính → báo cáo → gửi email SMTP → xếp hàng Zalo.

  python scripts/auto_run.py --mode live            # theo config/schedule.yaml
  python scripts/auto_run.py --mode dry-run         # không gửi gì

Cần: file nguồn có link công khai (xem fetch_sources.py) hoặc đã có sẵn trong inbox/ ; biến môi trường GMAIL_USER, GMAIL_APP_PASSWORD.
Zalo: không gửi được trong môi trường tự động -> ghi vào zalo-queue/pending.jsonl để agent/người dùng gửi bù khi bật máy.
Bất thường: chỉ gửi cảnh báo riêng cho người phụ trách (do run_report quyết định).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import send_mail  # noqa: E402
import zalo_queue  # noqa: E402
from sales_report.pipeline import run  # noqa: E402

SKILL = HERE.parent


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["dry-run", "test", "live"], default="dry-run")
    ap.add_argument("--inbox", default=str(SKILL / "inbox"))
    ap.add_argument("--out", default=str(SKILL / "out"))
    ap.add_argument("--config-dir", default=str(SKILL / "config"))
    ap.add_argument("--frequency", choices=["daily", "weekly"])
    ap.add_argument("--no-fetch", action="store_true", help="bỏ qua bước tải (file đã có trong inbox/)")
    a = ap.parse_args()

    if not a.no_fetch:
        r = subprocess.run([sys.executable, str(HERE / "fetch_sources.py"), "--out", a.inbox, "--config-dir", a.config_dir],
                           capture_output=True, text=True, encoding="utf-8")
        print(r.stdout.strip())
        if r.returncode:
            print(r.stderr.strip(), file=sys.stderr)
    res = run(a.inbox, a.out, a.config_dir, a.mode, None, None, a.frequency)
    print(f"Kỳ {res['period_title']} · trạng thái {res['status']} · {res['counts']}")
    for i in res["issues"]:
        print(f"  [{i['severity']}] {i['title']}")
    for act in (x for x in res["actions"] if x["channel"] == "sheet" and x["send"]):
        try:
            import sheets_sync
            for line in sheets_sync.push(json.loads(Path(act["file"]).read_text(encoding="utf-8")), act["spreadsheet_id"]):
                print("Sheet tổng hợp:", line)
        except Exception as e:  # noqa: BLE001 — Sheet lỗi không được chặn email
            print(f"KHÔNG GHI ĐƯỢC SHEET TỔNG HỢP: {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)
    if a.mode != "dry-run":
        print("Hàng đợi Zalo:", json.dumps([r["id"] for r in zalo_queue.add_from_result(res["result_path"])]))
    try:
        for line in send_mail.send_actions(res["result_path"]):
            print(line)
    except RuntimeError as e:
        print(f"KHÔNG GỬI ĐƯỢC EMAIL: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

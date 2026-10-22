#!/usr/bin/env python3
"""CLI: python scripts/run_report.py --inbox <thư mục file> [--mode dry-run|test|live] [--date YYYY-MM-DD]

In ra một bản tóm tắt ngắn; kế hoạch gửi đầy đủ nằm trong <out>/<ngày>/result.json.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sales_report.config import ConfigError  # noqa: E402
from sales_report.pipeline import MODES, run  # noqa: E402


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inbox", default=str(SKILL / "inbox"), help="thư mục chứa file đã tải về từ Drive/Sheets")
    ap.add_argument("--out", default=str(SKILL / "out"))
    ap.add_argument("--config-dir", default=str(SKILL / "config"))
    ap.add_argument("--mode", choices=MODES, default="dry-run",
                    help="dry-run: không gửi gì (mặc định) | test: chỉ gửi người phụ trách | live: gửi thật")
    ap.add_argument("--date", help="ngày báo cáo YYYY-MM-DD (mặc định: ngày làm việc trước đó)")
    ap.add_argument("--frequency", choices=["daily", "weekly"], help="daily: báo cáo ngày trước | weekly: báo cáo tuần trước (mặc định theo config)")
    ap.add_argument("--today", help="giả lập 'hôm nay' YYYY-MM-DD (dùng để kiểm thử)")
    a = ap.parse_args(argv)
    try:
        now = dt.datetime.combine(dt.date.fromisoformat(a.today), dt.time(8, 0)) if a.today else None
        res = run(a.inbox, a.out, a.config_dir, a.mode,
                  dt.date.fromisoformat(a.date) if a.date else None, now, a.frequency)
    except (ConfigError, ValueError, FileNotFoundError) as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 1
    c = res["counts"]
    print(f"Kỳ báo cáo   : {res['period_title']}   Chế độ: {res['mode']}")
    print(f"Trạng thái   : {res['status']}  (nghiêm trọng: {c['critical']}, lưu ý: {c['warnings']})")
    for i in res["issues"]:
        print(f"  [{i['severity']:<8}] {i['code']}: {i['title']}")
    if res["metrics"]:
        m = res["metrics"]
        print(f"Doanh thu kỳ {m['day_revenue']:,.0f} | lũy kế {m['mtd_revenue']:,.0f} | đạt MT {m['achieved_pct'] or 0:.1f}%")
    for act in res["actions"]:
        to = act.get("to") or act.get("target")
        print(f"  -> {act['channel']}/{act['kind']} tới {to}: {'GỬI' if act['send'] else 'bỏ qua (không gửi)'}")
    print(f"Kết quả      : {res['result_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

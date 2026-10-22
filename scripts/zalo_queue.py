#!/usr/bin/env python3
"""Hàng đợi Zalo dạng file (zalo-queue/pending.jsonl): chạy tự động không gửi được Zalo thì xếp hàng, gửi bù khi bật máy.

  python scripts/zalo_queue.py add out/2026-10-21/result.json     # xếp các tin Zalo (send=true) của kỳ vào hàng đợi
  python scripts/zalo_queue.py list                               # JSON các tin đang chờ
  python scripts/zalo_queue.py mark-sent <id> [<id> ...]          # đánh dấu đã gửi

Mỗi dòng: {id, created, report_date, title, target, text, status: pending|sent, sent_at}. Không trùng: cùng kỳ + cùng hội thoại chỉ xếp 1 lần.
Dùng chung được với Google Sheet "ZaloQueue" (cùng cột) khi chạy bằng connector.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
QUEUE = SKILL / "zalo-queue" / "pending.jsonl"


def load(path: Path = QUEUE) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def save(rows: list[dict], path: Path = QUEUE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def add_from_result(result_path: str, path: Path = QUEUE) -> list[dict]:
    res = json.loads(Path(result_path).read_text(encoding="utf-8"))
    rows, added = load(path), []
    have = {r["id"] for r in rows}
    for created, report_date, title, target, text, _status in res.get("zalo_queue_rows", []):
        rid = hashlib.sha1(f"{report_date}|{res.get('kind')}|{target}".encode()).hexdigest()[:10]
        if rid in have:
            continue
        row = {"id": rid, "created": created, "report_date": report_date, "title": title, "target": target,
               "text": text, "status": "pending", "sent_at": None}
        rows.append(row)
        added.append(row)
    save(rows, path)
    return added


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("result")
    sub.add_parser("list")
    p = sub.add_parser("mark-sent"); p.add_argument("ids", nargs="+")
    a = ap.parse_args()
    if a.cmd == "add":
        print(json.dumps({"added": [r["id"] for r in add_from_result(a.result)]}, ensure_ascii=False))
    elif a.cmd == "list":
        print(json.dumps([r for r in load() if r["status"] == "pending"], ensure_ascii=False, indent=2))
    else:
        rows = load()
        now = dt.datetime.now().isoformat(timespec="seconds")
        n = 0
        for r in rows:
            if r["id"] in a.ids and r["status"] == "pending":
                r["status"], r["sent_at"] = "sent", now
                n += 1
        save(rows)
        print(json.dumps({"marked": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

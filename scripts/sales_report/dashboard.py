"""Báo cáo HTML tương tác (1 file tự chứa): bộ lọc kỳ doanh thu, bấm vào từng người xem chi tiết.

Dữ liệu giao dịch được nhúng vào trang dưới dạng JSON; JavaScript chỉ tính lại để lọc/xem chi tiết.
Số liệu "chính thức" ở email vẫn do Python tính (metrics.py) — selftest đối chiếu hai bên.
"""
from __future__ import annotations

import datetime as dt
import json
from html import escape
from pathlib import Path

import pandas as pd

from .metrics import prepare

TEMPLATE = Path(__file__).with_name("dashboard_template.html")
HISTORY_DAYS = 120


def embed_data(df: pd.DataFrame, m: dict, cfg: dict, issues: list, n_files: int, generated: str, rd: dt.date) -> dict:
    sources = cfg["sources"]["sources"]
    owners = [s["owner"] for s in sources]
    d = prepare(df, owners)
    d = d[(d["date"] <= rd) & (d["date"] >= rd - dt.timedelta(days=HISTORY_DAYS))]
    sellers = list(dict.fromkeys(owners + sorted(set(d["seller"]) - set(owners))))
    targets = {s["owner"]: s.get("monthly_target") for s in sources}
    dates = sorted({x.isoformat() for x in d["date"]})
    di = {x: i for i, x in enumerate(dates)}
    products = sorted(set(d["product"]))
    pi = {x: i for i, x in enumerate(products)}
    si = {x: i for i, x in enumerate(sellers)}
    rows = [[di[r.date.isoformat()], si[r.seller], pi[r.product], round(float(r.quantity), 2), round(float(r.revenue))]
            for r in d.itertuples()]
    return {
        "brand": cfg["sources"].get("general", {}).get("brand", "Báo cáo doanh số"),
        "sheetUrl": m.get("summary_sheet_url", ""), "reportDate": rd.isoformat(), "kind": m["kind"], "periodTitle": m["period_title"], "weekday": m["weekday"], "month": m["month"], "pace": m["pace_pct"],
        "totalTarget": m["total_target"], "daysInMonth": m["days_in_month"], "generated": generated, "files": n_files,
        "sellers": [{"name": n, "target": targets.get(n)} for n in sellers],
        "products": products, "dates": dates, "rows": rows,
        "warnings": [i.title for i in issues if i.severity == "warning"],
    }


def dashboard_html(data: dict, banner: str = "") -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    d = data["reportDate"]
    html = html.replace("__DATE__", f"{d[8:10]}/{d[5:7]}/{d[:4]}").replace("__DATA__", payload)
    if banner:  # bản chạy thử / test: dải cảnh báo ở đầu trang
        html = html.replace('<div class="shell">', f'<div style="background:#ffe08a;color:#5a3d0a;text-align:center;font-weight:800;'
                            f'font-size:12px;padding:6px;">{escape(banner)}</div><div class="shell">', 1)
    return html

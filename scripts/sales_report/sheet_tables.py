"""Bảng kết quả để ghi vào Google Sheet tổng hợp (1 file cố định, link không đổi).

Trả về dict thuần (JSON được):
  tabs   : {tên tab: [[...], ...]}  — ghi đè toàn bộ tab mỗi lần chạy
  append : {tên tab: [dòng, ...]}   — nối thêm (lịch sử các kỳ báo cáo)
  headers: {tên tab: [tiêu đề]}     — tiêu đề dùng khi tab nối thêm còn trống
Số ghi dạng số (không chuỗi) để Sheet tính/vẽ biểu đồ được; phần trăm ghi theo điểm % (66.6 = 66,6%).
"""
from __future__ import annotations

import datetime as dt

from .metrics import WEEKDAYS, prepare

TAB_OVERVIEW, TAB_PEOPLE, TAB_PRODUCTS, TAB_DAYS, TAB_HISTORY = "Tổng quan", "Theo người", "Sản phẩm", "Theo ngày", "Lịch sử"
STATUS_VI = {"good": "Đúng/vượt tiến độ", "warn": "Hơi chậm", "bad": "Chậm tiến độ", "none": "Chưa đặt mục tiêu"}
HISTORY_HEADER = ["Thời điểm chạy", "Kỳ báo cáo", "Loại kỳ", "Doanh thu kỳ", "Kỳ trước", "% so kỳ trước", "Lũy kế tháng",
                  "Mục tiêu tháng", "% đạt mục tiêu", "Trạng thái dữ liệu", "Số lưu ý"]


def _r(x, n=0):
    return None if x is None else round(float(x), n)


def build(m: dict, df, cfg: dict, issues: list, generated: str, status: str) -> dict:
    rd = dt.date.fromisoformat(m["report_date"])
    start = dt.date.fromisoformat(m["period_start"])
    owners = [s["owner"] for s in cfg["sources"]["sources"]]
    d = prepare(df, owners)
    wstart = min(rd.replace(day=1), start)
    month = d[(d["date"] >= wstart) & (d["date"] <= rd)]
    lw = m["last_week"]

    overview = [["Chỉ số", "Giá trị"],
                ["Kỳ báo cáo", m["period_title"]], ["Cập nhật lúc", generated], ["Trạng thái dữ liệu", status],
                [f"Doanh thu {m['noun']}", _r(m["day_revenue"])], [f"Kỳ trước ({lw['label']})", _r(lw["revenue"])],
                ["% so với kỳ trước", _r(lw["pct"], 1)], ["Doanh thu lũy kế tháng", _r(m["mtd_revenue"])],
                ["Mục tiêu tháng (tổng)", _r(m["total_target"])], ["% đạt mục tiêu", _r(m["achieved_pct"], 1)],
                ["Tiến độ kỳ vọng (%)", _r(m["pace_pct"], 1)], ["Dự báo cuối tháng", _r(m["projected_month_end"])],
                ["Số dòng bán trong kỳ", m["day_lines"]], ["Số đơn vị bán trong kỳ", _r(m["day_units"])]]
    for i, t in enumerate(m["top_products_day"], 1):
        overview.append([f"Top {i} sản phẩm trong {m['noun']}", f"{t['name']} — {t['revenue']:,.0f}".replace(",", ".")])

    people = [["Hạng", "Người bán", f"Doanh thu {m['noun']}", "Kỳ trước", "% so kỳ trước", "Số dòng", "Đơn vị", "Lũy kế tháng",
               "Mục tiêu tháng", "% đạt mục tiêu", "Trạng thái"]]
    for i, p in enumerate(m["people"], 1):
        people.append([i, p["name"], _r(p["day_revenue"]), _r(p["last_week_day"]), _r(p["wow_pct"], 1), p["day_lines"], _r(p["day_units"]),
                       _r(p["mtd_revenue"]), p["target"], _r(p["achieved_pct"], 1), STATUS_VI[p["status"]]])
    people.append(["", "TỔNG", _r(m["day_revenue"]), _r(lw["revenue"]), _r(lw["pct"], 1), m["day_lines"], _r(m["day_units"]),
                   _r(m["mtd_revenue"]), m["total_target"], _r(m["achieved_pct"], 1), STATUS_VI[m["target_status"]]])

    cur = month[(month["date"] >= start) & (month["date"] <= rd)]
    g = month.groupby("pkey").agg(name=("product", lambda s: s.mode().iat[0]), rev=("revenue", "sum"), units=("quantity", "sum"))
    gc = cur.groupby("pkey").agg(rev=("revenue", "sum"), units=("quantity", "sum")).reindex(g.index).fillna(0)
    g = g.assign(c_rev=gc["rev"], c_units=gc["units"]).sort_values("rev", ascending=False)
    total = float(g["rev"].sum()) or 1.0
    products = [["Hạng", "Sản phẩm", f"Đơn vị ({m['noun']})", f"Doanh thu {m['noun']}", "Đơn vị (tháng)", "Doanh thu tháng", "Tỷ trọng tháng (%)"]]
    for i, (_, x) in enumerate(g.iterrows(), 1):
        products.append([i, x["name"], _r(x["c_units"]), _r(x["c_rev"]), _r(x["units"]), _r(x["rev"]), _r(x["rev"] / total * 100, 1)])

    names = [p["name"] for p in m["people"]]
    piv = month.pivot_table(index="date", columns="seller", values="revenue", aggfunc="sum", fill_value=0)
    cols = [n for n in names if n in piv.columns] + [c for c in piv.columns if c not in names]
    days = [["Ngày", "Thứ"] + cols + ["Tổng ngày"]]
    for dte, row in piv.iterrows():
        days.append([dte.isoformat(), WEEKDAYS[dte.weekday()]] + [_r(row[c]) for c in cols] + [_r(row[cols].sum())])

    hist = [generated, m["period_title"], "tuần" if m["kind"] == "week" else "ngày", _r(m["day_revenue"]), _r(lw["revenue"]),
            _r(lw["pct"], 1), _r(m["mtd_revenue"]), _r(m["total_target"]), _r(m["achieved_pct"], 1), status,
            sum(1 for i in issues if i.severity == "warning")]
    return {"tabs": {TAB_OVERVIEW: overview, TAB_PEOPLE: people, TAB_PRODUCTS: products, TAB_DAYS: days},
            "append": {TAB_HISTORY: [hist]}, "headers": {TAB_HISTORY: HISTORY_HEADER}}

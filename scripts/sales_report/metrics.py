"""Tính chỉ số báo cáo bằng Python/pandas (không dùng LLM để tính số)."""
from __future__ import annotations

import calendar
import datetime as dt
from collections import Counter
from typing import Optional

import pandas as pd

from .parsing import norm

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def weekday_vi(d: dt.date) -> str:
    return WEEKDAYS[d.weekday()]


def canon_seller(name: str, owners: list[str]) -> str:
    """Gộp 'Bình' / 'trần thị bình' về đúng tên người phụ trách khai trong sources.yaml."""
    n = norm(name)
    for o in owners:
        if norm(o) == n:
            return o
    toks = set(n.split())
    cands = [o for o in owners if toks and toks <= set(norm(o).split())]
    return cands[0] if len(cands) == 1 else name.strip()


def prepare(df: pd.DataFrame, owners: list[str]) -> pd.DataFrame:
    d = df.copy()
    d["revenue"] = pd.to_numeric(d["revenue"], errors="coerce").fillna(0.0)
    d["quantity"] = pd.to_numeric(d["quantity"], errors="coerce").fillna(0.0)
    d["seller"] = d["seller"].map(lambda s: canon_seller(s, owners))
    d["pkey"] = d["product"].map(norm)
    return d


def daily_series(d: pd.DataFrame, seller: Optional[str] = None) -> dict[dt.date, float]:
    x = d if seller is None else d[d["seller"] == seller]
    return x.groupby("date")["revenue"].sum().to_dict()


def period_series(d: pd.DataFrame, rd: dt.date, kind: str, seller: Optional[str] = None) -> dict[dt.date, float]:
    """Chuỗi doanh thu để so sánh: kind=day -> từng ngày; kind=week -> tổng từng tuần, khoá là ngày cuối tuần (rd - 7k)."""
    if kind == "day":
        return daily_series(d, seller)
    x = d if seller is None else d[d["seller"] == seller]
    daily = x.groupby("date")["revenue"].sum().to_dict()
    return {rd - dt.timedelta(days=7 * k): sum(daily.get(rd - dt.timedelta(days=7 * k - i), 0.0) for i in range(0, -7, -1))
            for k in range(0, 14)}


def baseline(series: dict, rd: dt.date, rule: dict, kind: str = "day") -> tuple[Optional[float], str]:
    """Mốc so sánh cho phát hiện lệch doanh thu: TB cùng thứ (hoặc cùng tuần) của N tuần trước."""
    weeks = int(rule.get("baseline_weeks", 4))
    method = rule.get("baseline_method", "same_weekday_avg")
    if method == "last_week_same_day":
        weeks = 1
    same = [series[rd - dt.timedelta(days=7 * k)] for k in range(1, weeks + 1)
            if series.get(rd - dt.timedelta(days=7 * k), 0) > 0]
    if len(same) >= (1 if method == "last_week_same_day" else 2):
        return sum(same) / len(same), (f"TB {len(same)} {weekday_vi(rd)} gần nhất" if kind == "day" else f"TB {len(same)} tuần gần nhất")
    n = int(rule.get("fallback_days", 7))
    recent = [v for k, v in sorted(series.items(), reverse=True) if k < rd and v > 0][:n]
    if len(recent) >= int(rule.get("min_history_points", 3)):
        return sum(recent) / len(recent), f"TB {len(recent)} {'ngày' if kind == 'day' else 'tuần'} có dữ liệu gần nhất"
    return None, "không đủ lịch sử để so sánh"


def _pct(cur: float, base: Optional[float]) -> Optional[float]:
    return None if not base else (cur - base) / base * 100.0


def _top_products(d: pd.DataFrame, n: int, rank_by: str) -> list[dict]:
    if d.empty:
        return []
    names = d.groupby("pkey")["product"].agg(lambda s: Counter(s).most_common(1)[0][0])
    g = d.groupby("pkey").agg(revenue=("revenue", "sum"), units=("quantity", "sum"))
    g["name"] = names
    g = g.sort_values(rank_by, ascending=False).head(n)
    total = float(d["revenue"].sum()) or 1.0
    return [{"name": r["name"], "revenue": float(r["revenue"]), "units": float(r["units"]),
             "share_pct": float(r["revenue"]) / total * 100} for _, r in g.iterrows()]


def _status(achieved: Optional[float], pace: float) -> str:
    if achieved is None:
        return "none"
    if achieved >= pace:
        return "good"
    return "warn" if achieved >= pace * 0.8 else "bad"


def period_bounds(rd: dt.date, kind: str) -> tuple[dt.date, dt.date]:
    """kind=day: [rd, rd]; kind=week: tuần Thứ Hai–Chủ Nhật kết thúc ở rd (rd là Chủ Nhật)."""
    return (rd, rd) if kind == "day" else (rd - dt.timedelta(days=6), rd)


def period_title(rd: dt.date, kind: str) -> str:
    if kind == "day":
        return f"{weekday_vi(rd)} {rd:%d/%m/%Y}"
    start, _ = period_bounds(rd, kind)
    return f"Tuần {start:%d/%m} – {rd:%d/%m/%Y}"


def compute(df: pd.DataFrame, rd: dt.date, cfg: dict, kind: str = "day") -> dict:
    gen = cfg["sources"].get("general", {})
    sources = cfg["sources"]["sources"]
    owners = [s["owner"] for s in sources]
    d = prepare(df, owners)
    rank_by = (gen.get("top_products") or {}).get("rank_by", "revenue")
    top_n = int((gen.get("top_products") or {}).get("count", 3))

    start, _ = period_bounds(rd, kind)
    shift = dt.timedelta(days=7)  # kỳ trước: cùng thứ tuần trước (ngày) hoặc tuần liền trước (tuần)
    pstart, pend = start - shift, rd - shift
    month_start = rd.replace(day=1)
    days_in_month = calendar.monthrange(rd.year, rd.month)[1]
    cur = d[(d["date"] >= start) & (d["date"] <= rd)]
    prev = d[(d["date"] >= pstart) & (d["date"] <= pend)]
    mtd = d[(d["date"] >= month_start) & (d["date"] <= rd)]

    targets = {s["owner"]: s.get("monthly_target") for s in sources}
    total_target = (cfg["sources"].get("targets") or {}).get("total_monthly") or         (sum(t for t in targets.values() if t) or None)
    pace = rd.day / days_in_month * 100.0

    cur_rev, mtd_rev, prev_rev = float(cur["revenue"].sum()), float(mtd["revenue"].sum()), float(prev["revenue"].sum())
    ach = mtd_rev / total_target * 100 if total_target else None

    people = []
    for name in dict.fromkeys(owners + sorted(set(d["seller"]) - set(owners))):
        sd, sm, sp = cur[cur["seller"] == name], mtd[mtd["seller"] == name], prev[prev["seller"] == name]
        s_cur, s_mtd, s_prev = float(sd["revenue"].sum()), float(sm["revenue"].sum()), float(sp["revenue"].sum())
        t = targets.get(name)
        a = s_mtd / t * 100 if t else None
        people.append({
            "name": name, "day_revenue": s_cur, "day_units": float(sd["quantity"].sum()),
            "day_lines": int(len(sd)), "mtd_revenue": s_mtd, "target": t, "achieved_pct": a,
            "status": _status(a, pace), "last_week_day": s_prev, "wow_pct": _pct(s_cur, s_prev),
            "share_pct": s_cur / cur_rev * 100 if cur_rev else 0.0,
        })
    people.sort(key=lambda p: p["day_revenue"], reverse=True)

    daily = daily_series(d)
    trend = []
    if kind == "day":
        for k in range(13, -1, -1):
            x = rd - dt.timedelta(days=k)
            trend.append({"date": x.isoformat(), "label": x.strftime("%d/%m"), "revenue": float(daily.get(x, 0.0))})
    else:
        weekly = period_series(d, rd, "week")
        for k in range(7, -1, -1):
            e = rd - dt.timedelta(days=7 * k)
            trend.append({"date": e.isoformat(), "label": (e - dt.timedelta(days=6)).strftime("%d/%m"),
                          "revenue": float(weekly.get(e, 0.0))})

    series = period_series(d, rd, kind)
    base, base_desc = baseline(series, rd, (cfg["rules"]["rules"].get("revenue_deviation") or {}), kind)
    prior_label = f"{weekday_vi(pend)} tuần trước" if kind == "day" else "tuần trước"
    out = {
        "kind": kind, "noun": "ngày" if kind == "day" else "tuần",
        "report_date": rd.isoformat(), "period_start": start.isoformat(), "period_end": rd.isoformat(),
        "period_title": period_title(rd, kind), "weekday": weekday_vi(rd), "month": rd.strftime("%m/%Y"),
        "days_elapsed": rd.day, "days_in_month": days_in_month, "pace_pct": pace,
        "day_revenue": cur_rev, "day_lines": int(len(cur)), "day_units": float(cur["quantity"].sum()),
        "mtd_revenue": mtd_rev, "total_target": total_target, "achieved_pct": ach,
        "target_status": _status(ach, pace),
        "projected_month_end": mtd_rev / rd.day * days_in_month,
        "gap_to_target": (total_target - mtd_rev) if total_target else None,
        "last_week": {"date": pend.isoformat(), "start": pstart.isoformat(), "weekday": weekday_vi(pend),
                      "label": prior_label, "revenue": prev_rev, "delta": cur_rev - prev_rev, "pct": _pct(cur_rev, prev_rev)},
        "week_to_date": {"revenue": cur_rev if kind == "week" else float(d[(d["date"] >= rd - dt.timedelta(days=rd.weekday())) & (d["date"] <= rd)]["revenue"].sum()),
                         "prev_revenue": prev_rev if kind == "week" else float(d[(d["date"] >= rd - dt.timedelta(days=rd.weekday() + 7)) & (d["date"] <= pend)]["revenue"].sum()),
                         "pct": None},
        "baseline": {"value": base, "desc": base_desc, "pct": _pct(cur_rev, base)},
        "top_products_day": _top_products(cur, top_n, rank_by),
        "top_products_mtd": _top_products(mtd, top_n, rank_by),
        "rank_by": rank_by, "people": people, "trend": trend,
    }
    w = out["week_to_date"]
    w["pct"] = _pct(w["revenue"], w["prev_revenue"])
    return out

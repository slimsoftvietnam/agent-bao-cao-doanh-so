"""Điều phối: nạp dữ liệu -> phát hiện bất thường -> tính chỉ số -> dựng báo cáo -> lập kế hoạch gửi.

Python KHÔNG tự gửi thư. Nó ghi result.json (kế hoạch gửi); agent (hoặc send_mail.py) thực hiện gửi
và bị chặn cứng: khi có bất thường nghiêm trọng, kế hoạch chỉ chứa người phụ trách.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from . import anomalies, dashboard, excel_export, metrics, render
from .config import load_config
from .loader import load_all
from .parsing import fmt_vnd

MODES = ("dry-run", "test", "live")
PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net")


def now_in_tz(tz_name: str, override: dt.datetime | None = None) -> dt.datetime:
    if override:
        return override
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(tz_name))
    except Exception:  # Windows thiếu tzdata
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=7)))


def pick_report_date(today: dt.date, gen: dict) -> dt.date:
    d = today - dt.timedelta(days=1)
    if gen.get("report_date_rule", "previous_business_day") == "previous_business_day":
        days = set(gen.get("business_days", [0, 1, 2, 3, 4, 5]))
        for _ in range(7):
            if d.weekday() in days:
                break
            d -= dt.timedelta(days=1)
    return d


def _dispatch(mode, status, cfg, subject, report_file, excel_file, email_file, compact_file, alert_file, zalo_file, zalo_alert_file, dd, brand):
    rec = cfg["recipients"]
    owner, team = rec["owner"], rec["team"]
    send = mode != "dry-run"
    tag = "[TEST] " if mode == "test" else ""
    acts: list[dict] = []
    owner_zalo = (owner.get("zalo") or {}).get("target")
    if status == "anomaly":
        acts.append({"channel": "gmail", "kind": "alert", "to": [owner["email"]], "cc": [],
                     "subject": f"{tag}[CẢNH BÁO] Báo cáo doanh số {dd} bị giữ lại – cần kiểm tra dữ liệu",
                     "body_html_file": alert_file, "send": send})
        if owner_zalo:
            acts.append({"channel": "zalo", "kind": "alert", "target": owner_zalo, "text_file": zalo_alert_file, "send": send})
    elif mode == "live":
        acts.append({"channel": "gmail", "kind": "report", "to": list(team["to"]), "cc": list(team.get("cc") or []),
                     "subject": subject, "body_html_file": email_file, "body_compact_file": compact_file, "attachments": [report_file, excel_file], "send": True})
        if team.get("zalo_group"):
            acts.append({"channel": "zalo", "kind": "report", "target": team["zalo_group"], "text_file": zalo_file, "send": True})
    else:  # dry-run hoặc test: không bao giờ chạm tới nhóm
        acts.append({"channel": "gmail", "kind": "report", "to": [owner["email"]], "cc": [],
                     "subject": f"{tag or '[CHẠY THỬ] '}{subject}", "body_html_file": email_file, "body_compact_file": compact_file, "attachments": [report_file, excel_file], "send": send})
        if owner_zalo:
            acts.append({"channel": "zalo", "kind": "report", "target": owner_zalo, "text_file": zalo_file, "send": send})
    # Chốt chặn an toàn
    team_addrs = {a.lower() for a in list(team["to"]) + list(team.get("cc") or [])} - {owner["email"].lower()}
    for a in acts:
        if a["channel"] == "gmail" and (status == "anomaly" or mode != "live"):
            assert not (team_addrs & {x.lower() for x in a["to"] + a["cc"]}), "Chốt chặn: không được gửi cho nhóm"
        if a["channel"] == "zalo" and (status == "anomaly" or mode != "live"):
            assert a["target"] != team.get("zalo_group") or a["target"] == owner_zalo, "Chốt chặn: Zalo nhóm bị chặn"
    return acts


def pick_report_week_end(today: dt.date) -> dt.date:
    """Báo cáo tuần: Chủ Nhật gần nhất TRƯỚC hôm nay (chạy sáng thứ Hai -> tuần vừa kết thúc hôm qua)."""
    back = (today.weekday() + 1) % 7 or 7
    return today - dt.timedelta(days=back)


def run(inbox: str | Path, out_dir: str | Path, config_dir: str | Path, mode: str = "dry-run",
        report_date: dt.date | None = None, now: dt.datetime | None = None, frequency: str | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode phải là một trong {MODES}")
    cfg = load_config(config_dir)
    gen = cfg["sources"].get("general", {})
    brand = gen.get("brand", "Báo cáo doanh số")
    now = now_in_tz(gen.get("timezone", "Asia/Ho_Chi_Minh"), now)
    kind = "week" if (frequency or gen.get("frequency", "daily")) in ("week", "weekly") else "day"
    if kind == "week":
        rd = report_date or pick_report_week_end(now.date())
        rd = rd + dt.timedelta(days=6 - rd.weekday())  # luôn là Chủ Nhật kết thúc tuần chứa ngày được chọn
    else:
        rd = report_date or pick_report_date(now.date(), gen)
    dd = rd.strftime("%d/%m/%Y")
    title = metrics.period_title(rd, kind)

    if mode == "live":
        bad = [a for a in [cfg["recipients"]["owner"]["email"], *cfg["recipients"]["team"]["to"]]
               if a.lower().split("@")[-1] in PLACEHOLDER_DOMAINS]
        if bad:
            raise ValueError(f"Chế độ live bị chặn: recipients.yaml còn địa chỉ mẫu {bad}. Hãy thay bằng email thật.")

    inbox, out = Path(inbox), Path(out_dir) / rd.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    load = load_all(inbox, cfg)
    issues, dev = anomalies.detect(load, cfg, rd, kind)
    summ = anomalies.summarize(issues)
    status = summ["status"]

    files_info = [f"{f.name} — nguồn {f.source_id}: {f.n_rows} dòng"
                  + (f" (sheet: {', '.join(f.sheets_used)})" if f.sheets_used else " (không đọc được dữ liệu)")
                  for f in load.files] + [f"{f.name} — không thuộc nguồn nào" for f in load.unmatched]
    banner = banner_text = ""
    if mode != "live":
        banner_text = ("BẢN CHẠY THỬ" if mode == "dry-run" else "BẢN TEST – chỉ gửi người phụ trách") + " – không phải báo cáo chính thức"
        banner = ('<tr><td bgcolor="#fde68a" style="background:#fde68a;color:#78350f;text-align:center;font:600 12px Arial;padding:6px;">'
                  f'{"BẢN CHẠY THỬ" if mode == "dry-run" else "BẢN TEST – chỉ gửi người phụ trách"}'
                  ' – không phải báo cáo chính thức</td></tr>')

    m = None
    result_files = {}
    subject = f"{(cfg['recipients'].get('email') or {}).get('subject_prefix', '[Báo cáo doanh số]')} {title}"
    if status != "anomaly":
        m = metrics.compute(load.data, rd, cfg, kind)
        subject += f" – {fmt_vnd(m['day_revenue'])}"
        data = dashboard.embed_data(load.data, m, cfg, issues, len(load.files), now.strftime("%H:%M %d/%m/%Y"), rd)
        (out / "report.html").write_text(dashboard.dashboard_html(data, banner_text), encoding="utf-8")
        xlsx = excel_export.build_workbook(out / f"Tong-hop-doanh-so-{rd.isoformat()}.xlsx", load.data, m, cfg, issues, files_info)
        (out / "email.html").write_text(render.report_html(m, issues, brand, banner), encoding="utf-8")
        (out / "email_compact.html").write_text(render.compact_email_html(m, brand, banner_text), encoding="utf-8")
        (out / "zalo_report.txt").write_text(render.zalo_text(m), encoding="utf-8")
        result_files.update(report="report.html", email="email.html", email_compact="email_compact.html", excel=xlsx.name, zalo="zalo_report.txt")
    if issues:
        (out / "alert.html").write_text(render.alert_html(rd.isoformat(), issues, files_info, brand, banner, title), encoding="utf-8")
        result_files["alert"] = "alert.html"
    if status == "anomaly":
        (out / "zalo_alert.txt").write_text(render.zalo_alert_text(rd.isoformat(), issues, title), encoding="utf-8")
        result_files["zalo_alert"] = "zalo_alert.txt"

    def p(name):
        return str(out / name)

    actions = _dispatch(mode, status, cfg, subject, p("report.html"), p(f"Tong-hop-doanh-so-{rd.isoformat()}.xlsx"), p("email.html"), p("email_compact.html"), p("alert.html"),
                        p("zalo_report.txt"), p("zalo_alert.txt"), dd, brand)
    result = {
        "kind": kind, "period_title": title, "smtp_available": bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")),
        "report_date": rd.isoformat(), "generated_at": now.isoformat(timespec="seconds"), "mode": mode,
        "status": status, "send_team_report": status != "anomaly" and mode == "live",
        "counts": summ, "issues": [i.as_dict() for i in issues], "deviation": dev,
        "files": files_info, "metrics": m, "outputs": {k: p(v) for k, v in result_files.items()},
        "actions": actions,
        # Hàng đợi Zalo: nếu bước gửi Zalo thất bại (phiên đám mây không có Zalo Web), agent ghi dòng này vào Google Sheet hàng đợi
        "zalo_queue_rows": [[now.isoformat(timespec="seconds"), rd.isoformat(), title, a["target"],
                             Path(a["text_file"]).read_text(encoding="utf-8"), "pending"]
                            for a in actions if a["channel"] == "zalo" and a["send"]],
        "audit_row": [now.isoformat(timespec="seconds"), rd.isoformat(), mode, status,
                      round(m["day_revenue"]) if m else "", round(m["mtd_revenue"]) if m else "",
                      summ["critical"], summ["warnings"], "; ".join(f"{a['channel']}:{a['kind']}:{'sent' if a['send'] else 'skipped'}" for a in actions)],
    }
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    result["result_path"] = p("result.json")
    return result

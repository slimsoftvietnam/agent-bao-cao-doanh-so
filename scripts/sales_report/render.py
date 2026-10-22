"""Dựng báo cáo HTML (email-safe: bảng + CSS nội tuyến, không JS/SVG), email cảnh báo và tin Zalo."""
from __future__ import annotations

import re
from html import escape as e

from .parsing import fmt_pct, fmt_short, fmt_vnd

NAVY, TEAL, GREEN, AMBER, RED = "#1f1b5c", "#3949ab", "#2e9e6b", "#e09a2b", "#d64545"
ORANGE, PAPER, LINE = "#3949ab", "#ffffff", "#e3e6ee"
STATUS_COLOR = {"good": GREEN, "warn": AMBER, "bad": RED, "none": "#94a3b8"}
FONT = "font-family:'K2D','Segoe UI',Roboto,Arial,sans-serif;"


def _cell(bg, inner="&nbsp;", **attrs):
    """Ô bảng có màu nền: dùng thuộc tính bgcolor + background-color vì Gmail hay bỏ thuộc tính CSS `background`."""
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return f'<td bgcolor="{bg}"{extra} style="background-color:{bg};">{inner}</td>'


def _bar(pct, color, pace=None, h=10):
    """Thanh tiến độ dạng bảng 2 ô (không dùng position/absolute — Gmail không hỗ trợ)."""
    w = max(1, min(100, round(pct or 0)))
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            + f'<td width="{w}%" height="{h}" bgcolor="{color}" style="background-color:{color};font-size:1px;line-height:{h}px;">&nbsp;</td>'
            + f'<td bgcolor="#e2e8f0" style="background-color:#e2e8f0;font-size:1px;line-height:{h}px;">&nbsp;</td></tr></table>')


def _badge(text, bg, fg, size):
    """Hình tròn/vuông bo góc chứa chữ, dựng bằng bảng để giữ nền khi Gmail lọc CSS."""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0"><tr><td bgcolor="{bg}" width="{size}" height="{size}" align="center" '
            f'valign="middle" style="background-color:{bg};color:{fg};font-weight:700;font-size:{size // 2 + 1}px;border-radius:{size // 2}px;'
            f'width:{size}px;height:{size}px;">{text}</td></tr></table>')


def _insights(m: dict) -> list[str]:
    out = []
    lw = m["last_week"]
    if lw["pct"] is not None:
        out.append(f"Doanh thu {m['noun']} {fmt_pct(lw['pct'], True)} so với {lw['label']} "
                   f"({fmt_short(lw['revenue'])} → {fmt_short(m['day_revenue'])}).")
    if m["people"] and m["people"][0]["day_revenue"] > 0:
        p = m["people"][0]
        out.append(f"{p['name']} dẫn đầu ngày với {fmt_short(p['day_revenue'])} ({p['share_pct']:.0f}% tổng).")
    if m["top_products_day"]:
        t = m["top_products_day"][0]
        out.append(f"Sản phẩm số 1: {t['name']} — {fmt_short(t['revenue'])}, {t['units']:.0f} đơn vị.")
    behind = [p["name"] for p in m["people"] if p["status"] == "bad"]
    if behind:
        out.append(f"Cần đẩy nhanh tiến độ: {', '.join(behind)} (thấp hơn 80% tiến độ kỳ vọng {m['pace_pct']:.0f}%).")
    if m["total_target"] and m["projected_month_end"]:
        out.append(f"Với nhịp hiện tại, dự báo cuối tháng ≈ {fmt_short(m['projected_month_end'])} "
                   f"({m['projected_month_end'] / m['total_target'] * 100:.0f}% mục tiêu).")
    return out


def _chip(text, fg, bg):
    return (f'<span style="display:inline-block;background:{bg};color:{fg};font-size:11px;font-weight:700;'
            f'padding:3px 9px;border-radius:999px;white-space:nowrap;">{text}</span>')


def _delta_chip(p, on_dark=False):
    if p is None:
        return _chip("n/a", "#475569", "#e2e8f0")
    up = p >= 0
    txt = f'{"▲" if up else "▼"} {fmt_pct(abs(p))}'
    if on_dark:
        return _chip(txt, "#ffffff", "#2e9e6b" if up else "#d64545")
    return _chip(txt, "#166534" if up else "#991b1b", "#dcfce7" if up else "#fee2e2")


STATUS_LABEL = {"good": ("Đúng/vượt tiến độ", "#166534", "#dcfce7"), "warn": ("Hơi chậm", "#92400e", "#fef3c7"),
                "bad": ("Chậm tiến độ", "#991b1b", "#fee2e2"), "none": ("Chưa đặt MT", "#475569", "#e2e8f0")}
AVATARS = ["#1f1b5c", "#3949ab", "#7986cb", "#b3bbe6", "#00838f", "#4db6ac", "#f2a65a", "#e57373", "#9575cd", "#8d6e63"]
MEDALS = [("#f59e0b", "#fef3c7"), ("#94a3b8", "#f1f5f9"), ("#b45309", "#ffedd5")]


def _initial(name):
    return e(name.split()[-1][:1].upper())


def _section(title, sub=""):
    s = f'<span style="font-size:12px;font-weight:400;color:#94a3b8;margin-left:8px;">{e(sub)}</span>' if sub else ""
    return (f'<div style="font-size:16px;font-weight:700;color:{NAVY};margin:0 0 14px;">'
            f'<span style="display:inline-block;width:4px;height:16px;background:{TEAL};border-radius:2px;'
            f'vertical-align:-2px;margin-right:8px;"></span>{e(title)}{s}</div>')


def _gmail_safe(html: str) -> str:
    """Gmail bỏ thuộc tính `background:` rút gọn: đổi sang `background-color:` và thêm bgcolor cho ô/bảng còn thiếu."""
    html = re.sub(r"background:(#[0-9a-fA-F]{3,8})", r"background-color:", html)
    def add_bgcolor(m):
        tag = m.group(0)
        if "bgcolor=" in tag:
            return tag
        c = re.search(r"background-color:(#[0-9a-fA-F]{3,8})", tag)
        return tag.replace(">", f' bgcolor="{c.group(1)}">', 1) if c else tag
    return re.sub(r"<(?:td|table)[^>]*>", add_bgcolor, html)


def report_html(m: dict, issues: list, brand: str, test_banner: str = "") -> str:
    rd = m["report_date"]
    dd = f"{rd[8:10]}/{rd[5:7]}/{rd[:4]}"
    ach, pace = m["achieved_pct"], m["pace_pct"]
    acol = STATUS_COLOR[m["target_status"]]
    lw, wtd = m["last_week"], m["week_to_date"]
    card = ('style="background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(31,27,92,.1);padding:20px 22px;"')

    # ---- Hero
    hero = f"""<tr><td bgcolor="{NAVY}" style="background:{NAVY};
border-radius:22px;padding:26px 28px 24px;color:#ffffff;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#c5cae9;font-weight:800;">{e(brand)} · Báo cáo doanh số</td>
<td align="right"><span style="background:#3b3880;color:#ffffff;border-radius:999px;padding:5px 12px;font-size:12px;font-weight:600;">
{m['period_title']}</span></td></tr></table>
<div style="font-size:13px;color:#c9d6d0;margin-top:18px;">Doanh thu {m['noun']} này</div>
<div style="font-size:44px;line-height:1.1;font-weight:800;margin:4px 0 10px;letter-spacing:-.02em;">{fmt_vnd(m['day_revenue'])}</div>
<div style="font-size:13px;color:#e6ede9;">{_delta_chip(lw['pct'], True)}
&nbsp;so với {lw['label']} ({fmt_vnd(lw['revenue'])}) &nbsp;·&nbsp; {m['day_lines']} dòng, {m['day_units']:.0f} đơn vị</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px;border-top:1px solid #4a4780;">
<tr><td width="33%" style="padding-top:14px;"><div style="font-size:11px;color:#c9d6d0;text-transform:uppercase;letter-spacing:.06em;">Lũy kế tháng {m['month']}</div>
<div style="font-size:20px;font-weight:700;margin-top:3px;">{fmt_short(m['mtd_revenue'])}</div></td>
<td width="33%" style="padding-top:14px;"><div style="font-size:11px;color:#c9d6d0;text-transform:uppercase;letter-spacing:.06em;">Đạt mục tiêu</div>
<div style="font-size:20px;font-weight:700;margin-top:3px;">{fmt_pct(ach) if ach is not None else 'n/a'}</div></td>
<td width="34%" style="padding-top:14px;"><div style="font-size:11px;color:#c9d6d0;text-transform:uppercase;letter-spacing:.06em;">Dự báo cuối tháng</div>
<div style="font-size:20px;font-weight:700;margin-top:3px;">{fmt_short(m['projected_month_end'])}</div></td></tr></table></td></tr>"""

    # ---- Tiến độ mục tiêu
    gap = m["gap_to_target"]
    goal = f"""<tr><td style="padding-top:14px;"><div {card}>{_section("Tiến độ mục tiêu tháng")}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font-size:30px;font-weight:800;color:{acol};">{fmt_pct(ach) if ach is not None else 'n/a'}</td>
<td align="right" style="font-size:13px;color:#475569;">{fmt_vnd(m['mtd_revenue'])}
{'<span style="color:#94a3b8;"> / ' + fmt_vnd(m['total_target']) + '</span>' if m['total_target'] else ''}</td></tr></table>
<div style="margin:12px 0 6px;">{_bar(ach, acol, pace, 14)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:12px;color:#64748b;"><tr>
<td>Tiến độ kỳ vọng ở ngày này: <b style="color:{NAVY};">{pace:.0f}%</b> (ngày {m['days_elapsed']}/{m['days_in_month']})</td>
<td align="right">{('Còn thiếu <b style="color:' + NAVY + ';">' + fmt_short(gap) + '</b>') if gap and gap > 0 else '<b style="color:' + GREEN + ';">Đã vượt mục tiêu</b>' if gap is not None else ''}</td></tr></table>
{('<div style="margin-top:12px;padding:10px 12px;background:#f1f5f9;border-radius:10px;font-size:12px;color:#334155;">'
  '📈 Dự báo cuối tháng với nhịp hiện tại: <b>' + fmt_short(m['projected_month_end']) + '</b> (' +
  f"{m['projected_month_end'] / m['total_target'] * 100:.0f}" + '% mục tiêu)</div>') if m['total_target'] else ''}</div></td></tr>"""

    # ---- Theo người
    cards = []
    for i, p in enumerate(m["people"]):
        lab, fg, bg = STATUS_LABEL[p["status"]]
        prog = (f'{_bar(p["achieved_pct"], STATUS_COLOR[p["status"]], pace, 8)}'
                f'<div style="font-size:11px;color:#64748b;margin-top:5px;">Lũy kế {fmt_short(p["mtd_revenue"])} · '
                f'đạt <b style="color:{NAVY};">{fmt_pct(p["achieved_pct"])}</b> / MT {fmt_short(p["target"])}</div>'
                if p["target"] else f'<div style="font-size:11px;color:#64748b;">Lũy kế {fmt_short(p["mtd_revenue"])}</div>')
        cards.append(f"""<tr><td style="padding:12px 0;border-top:{'0' if i == 0 else '1px solid #eef2f7'};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="46" valign="top">{_badge(_initial(p['name']), AVATARS[i % len(AVATARS)], "#ffffff", 38)}</td>
<td valign="top"><div style="font-weight:700;font-size:14px;color:{NAVY};">{e(p['name'])}
&nbsp;{_chip(lab, fg, bg)}</div><div style="margin-top:8px;">{prog}</div></td>
<td width="150" align="right" valign="top"><div style="font-size:17px;font-weight:800;color:{NAVY};">{fmt_vnd(p['day_revenue'])}</div>
<div style="margin-top:4px;">{_delta_chip(p['wow_pct'])}</div>
<div style="font-size:11px;color:#94a3b8;margin-top:3px;">{p['share_pct']:.0f}% tổng ngày</div></td></tr></table></td></tr>""")
    people = (f'<tr><td style="padding-top:14px;"><div {card}>{_section("Doanh thu từng người", "so với " + lw["label"])}'
              f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(cards)}</table></div></td></tr>')

    # ---- Top sản phẩm
    def prods(items):
        if not items:
            return '<div style="color:#64748b;font-size:13px;">Không có dữ liệu</div>'
        top = max(t["revenue"] for t in items) or 1
        out = []
        for i, t in enumerate(items):
            fg, bg = MEDALS[i % 3]
            out.append(f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;"><tr>
<td width="36" valign="top">{_badge(i + 1, bg, fg, 28)}</td>
<td valign="top"><div style="font-size:13px;font-weight:600;color:#1e293b;">{e(t['name'])}</div>
<div style="margin-top:6px;">{_bar(t['revenue'] / top * 100, TEAL, None, 6)}</div></td>
<td width="130" align="right" valign="top"><div style="font-size:14px;font-weight:700;color:{NAVY};">{fmt_vnd(t['revenue'])}</div>
<div style="font-size:11px;color:#94a3b8;">{t['units']:.0f} đơn vị · {t['share_pct']:.0f}%</div></td></tr></table>""")
        return "".join(out)

    products = (f'<tr><td style="padding-top:14px;"><div {card}>{_section("Top 3 sản phẩm trong " + m["noun"])}{prods(m["top_products_day"])}'
                f'<div style="height:1px;border-top:1px solid #eceef3;margin:6px 0 16px;font-size:1px;">&nbsp;</div>{_section("Top 3 sản phẩm lũy kế tháng")}'
                f'{prods(m["top_products_mtd"])}</div></td></tr>')

    # ---- Xu hướng
    mx = max([t["revenue"] for t in m["trend"]] + [1])
    bars = ""
    for t in m["trend"]:
        today, was = t["date"] == rd, t["date"] == lw["date"]
        col = TEAL if today else ("#7986cb" if was else "#cbd5e1")
        lbl = f'<div style="font-size:10px;font-weight:700;color:{NAVY};">{fmt_short(t["revenue"]).replace(" tr", "")}</div>' if today or was else ""
        bars += (f'<td valign="bottom" align="center" style="padding:0 2px;height:130px;">{lbl}'
                 f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td height="{max(3, round(t["revenue"] / mx * 90))}" bgcolor="{col}" '
                 f'style="background-color:{col};font-size:1px;line-height:1px;">&nbsp;</td></tr></table></td>')
    labels = "".join(f'<td align="center" style="padding:4px 0 0;font-size:10px;color:{NAVY if t["date"] == rd else "#94a3b8"};'
                     f'font-weight:{700 if t["date"] == rd else 400};">{t["label"]}</td>' for t in m["trend"])
    trend = (f'<tr><td style="padding-top:14px;"><div {card}>{_section("Xu hướng " + ("14 ngày" if m["kind"] == "day" else "8 tuần"), "triệu đồng")}'
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{bars}</tr><tr>{labels}</tr></table>'
             f'<div style="font-size:11px;color:#64748b;margin-top:10px;"><span style="color:{TEAL};">■</span> Kỳ này &nbsp;'
             f'<span style="color:#7986cb;">■</span> Kỳ trước &nbsp;<span style="color:#cbd5e1;">■</span> Các kỳ khác</div></div></td></tr>')

    # ---- Điểm nhấn + ghi chú
    ins = "".join(f'<tr><td width="26" valign="top" style="padding:6px 0;font-size:15px;">{ic}</td>'
                  f'<td style="padding:6px 0;font-size:13px;line-height:1.5;color:#334155;">{e(t)}</td></tr>'
                  for ic, t in zip(["💡", "🏆", "⭐", "⚠️", "📈"], _insights(m)))
    insights = (f'<tr><td style="padding-top:14px;"><div style="background:#e8eaf6;border:1px solid #e3e6ee;border-radius:16px;padding:18px 22px;">'
                f'{_section("Điểm nhấn")}<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{ins}</table></div></td></tr>')
    warns = [i for i in issues if i.severity == "warning"]
    note = ""
    if warns:
        note = ('<tr><td style="padding-top:14px;"><div style="padding:12px 16px;background:#fffbeb;border-left:4px solid #f59e0b;'
                'border-radius:8px;font-size:12px;color:#78350f;"><b>Ghi chú chất lượng dữ liệu</b><ul style="margin:6px 0 0 18px;padding:0;">'
                + "".join(f"<li>{e(i.title)}</li>" for i in warns) + "</ul></div></td></tr>")

    sheet = (f' &nbsp;·&nbsp; 📊 <a href="{e(m["summary_sheet_url"])}" style="color:#3949ab;font-weight:700;">Mở bảng tổng hợp Google Sheets</a>'
             if m.get("summary_sheet_url") else "")
    cta = (f'<tr><td style="padding-top:14px;"><div style="background:#e8eaf6;border:1px solid {LINE};border-radius:16px;padding:14px 18px;'
           f'font-size:13px;color:#334155;">📎 <b>Mở file đính kèm</b> <span style="color:{ORANGE};font-weight:700;">Bao-cao-doanh-so-{rd}.html</span> '
           f'bằng trình duyệt để <b>lọc theo kỳ doanh thu</b> và <b>bấm vào từng người</b> xem chi tiết sản phẩm, ngày bán, giao dịch.{sheet}</div></td></tr>')
    html = f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Báo cáo doanh số {m['period_title']}</title></head>
<body style="margin:0;background:#eceef3;{FONT}color:#1e293b;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#eceef3"><tr><td align="center" bgcolor="#eceef3" style="padding:20px 10px;">
<table role="presentation" width="680" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%;">
{test_banner}{hero}{cta}{goal}{people}{products}{trend}{insights}{note}
<tr><td align="center" style="padding:18px 0 4px;font-size:11px;color:#94a3b8;line-height:1.6;">
Tạo tự động bởi AI Agent báo cáo doanh số · số liệu tính bằng Python từ các file nguồn<br>{m['period_title']} · {e(brand)}</td></tr>
</table></td></tr></table></body></html>"""
    return _gmail_safe(html)


def alert_html(rd_iso: str, issues: list, files_info: list[str], brand: str, test_banner: str = "", title: str = "") -> str:
    dd = title or f"{rd_iso[8:10]}/{rd_iso[5:7]}/{rd_iso[:4]}"
    crit = [i for i in issues if i.severity == "critical"]
    other = [i for i in issues if i.severity != "critical"]
    col = {"critical": RED, "warning": AMBER, "info": "#64748b"}
    lab = {"critical": "NGHIÊM TRỌNG", "warning": "LƯU Ý", "info": "THÔNG TIN"}

    def row(i):
        return (f'<tr><td style="padding:12px 0;border-top:1px solid #e2e8f0;"><b style="color:{col[i.severity]};'
                f'font-size:11px;letter-spacing:.04em;">{lab[i.severity]}</b> '
                f'<span style="font-size:11px;color:#64748b;">{e(i.code)}</span>'
                f'<div style="font-weight:600;margin:6px 0 2px;color:{NAVY};">{e(i.title)}</div>'
                f'<div style="font-size:13px;color:#475569;">{e(i.detail)}</div>'
                f'<div style="font-size:13px;margin-top:4px;color:#166534;">➜ {e(i.action)}</div></td></tr>')

    html = f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>Cảnh báo dữ liệu {dd}</title></head>
<body style="margin:0;background:#fef2f2;{FONT}color:#1e293b;"><table role="presentation" width="100%" bgcolor="#fef2f2"><tr><td align="center" bgcolor="#fef2f2" style="padding:16px 8px;">
<table role="presentation" width="640" style="max-width:640px;width:100%;">{test_banner}
<tr><td bgcolor="{RED}" style="background:{RED};border-radius:14px 14px 0 0;padding:20px 24px;color:#fff;">
<div style="font-size:12px;letter-spacing:.1em;opacity:.85;">{e(brand)} · CẢNH BÁO RIÊNG CHO NGƯỜI PHỤ TRÁCH</div>
<div style="font-size:22px;font-weight:700;margin-top:4px;">Báo cáo doanh số {dd} đã bị GIỮ LẠI</div></td></tr>
<tr><td style="background:#fff;padding:18px 24px;border-radius:0 0 14px 14px;">
<p style="margin:0 0 8px;font-size:14px;">Phát hiện <b>{len(crit)}</b> vấn đề nghiêm trọng. Báo cáo <b>chưa được gửi cho nhóm</b>;
chỉ bạn nhận email này. Sau khi sửa dữ liệu, chạy lại skill để phát hành.</p>
<table role="presentation" width="100%">{''.join(row(i) for i in crit + other)}</table>
<div style="margin-top:14px;padding:10px 12px;background:#f1f5f9;border-radius:8px;font-size:12px;color:#475569;">
<b>File đã nhận:</b><br>{'<br>'.join(e(x) for x in files_info) or '(không có)'}</div></td></tr></table></td></tr></table></body></html>"""
    return _gmail_safe(html)


def reminder_html(staff_name: str, period_title: str, where: str, brand: str, owner_name: str) -> str:
    """Thư nhắc nhân viên cập nhật số liệu (gửi khi kỳ báo cáo thiếu dữ liệu của người đó)."""
    html = (f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#eceef3"><tr><td align="center" bgcolor="#eceef3" style="padding:18px 10px;font-family:'Segoe UI',Roboto,Arial,sans-serif;color:#262a41">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%"><tr><td bgcolor="#1f1b5c" style="background-color:#1f1b5c;color:#ffffff;padding:20px 24px">
<div style="font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#c5cae9;font-weight:700">{e(brand)} · Nhắc cập nhật số liệu</div>
<div style="font-size:20px;font-weight:800;margin-top:6px;color:#ffffff">Chào {e(staff_name)}, cần cập nhật doanh số</div></td></tr>
<tr><td bgcolor="#ffffff" style="background-color:#ffffff;padding:20px 24px;font-size:14px;line-height:1.6">
Báo cáo doanh số <b>{e(period_title)}</b> chưa phát hành được vì <b>chưa có số liệu của bạn</b> trong kỳ này.<br><br>
Vui lòng cập nhật doanh số vào: <b>{e(where)}</b>.<br><br>
Sau khi cập nhật, báo cáo sẽ tự gửi ở lần chạy kế tiếp (hoặc nhờ {e(owner_name)} chạy lại ngay).</td></tr></table></td></tr></table>''')
    return _gmail_safe(html)


def zalo_text(m: dict) -> str:
    rd = m["report_date"]
    dd = f"{rd[8:10]}/{rd[5:7]}/{rd[:4]}"
    lw = m["last_week"]
    lines = [f"📊 BÁO CÁO DOANH SỐ – {m['period_title']}",
             f"• Doanh thu {m['noun']}: {fmt_short(m['day_revenue'])} ({fmt_pct(lw['pct'], True)} so với {lw['label']})",
             f"• Lũy kế tháng: {fmt_short(m['mtd_revenue'])}"
             + (f" – đạt {fmt_pct(m['achieved_pct'])} mục tiêu (kỳ vọng {m['pace_pct']:.0f}%)" if m["achieved_pct"] is not None else "")]
    if m["top_products_day"]:
        lines.append("• Top 3: " + "; ".join(f"{i}) {t['name']} {fmt_short(t['revenue'])}"
                                              for i, t in enumerate(m["top_products_day"], 1)))
    lines.append("• Theo người: " + " | ".join(f"{p['name'].split()[-1]} {fmt_short(p['day_revenue'])}" for p in m["people"]))
    lines.append("Chi tiết xem email “Báo cáo doanh số”" + (f" hoặc bảng tổng hợp: {m['summary_sheet_url']}" if m.get("summary_sheet_url") else "") + ".")
    return "\n".join(lines)


def zalo_alert_text(rd_iso: str, issues: list, title: str = "") -> str:
    crit = [i for i in issues if i.severity == "critical"]
    return (f"⚠️ CẢNH BÁO: báo cáo doanh số {title or rd_iso[8:10] + "/" + rd_iso[5:7]} bị giữ lại ({len(crit)} vấn đề).\n"
            + "\n".join(f"- {i.title}" for i in crit[:6]) + "\nChi tiết đã gửi qua email riêng.")


def compact_email_html(m: dict, brand: str, banner_text: str = "") -> str:
    """Thư rút gọn (~6KB) để dán vào công cụ Gmail của connector khi không có SMTP; vẫn đủ số liệu chính."""
    lw = m["last_week"]
    up = (lw["pct"] or 0) >= 0

    def money(x):
        return f"{x:,.0f}".replace(",", ".")

    def wow(p):
        if p["wow_pct"] is None:
            return "n/a"
        return ("▲ " if p["wow_pct"] >= 0 else "▼ ") + fmt_pct(abs(p["wow_pct"]))

    col = {"good": "#1e7f55", "warn": "#b07410", "bad": "#c03434", "none": "#64748b"}
    rows = "".join(
        f'<tr style="border-top:1px solid #e3e6ee"><td>{e(p["name"])}</td><td align="right"><b>{money(p["day_revenue"])}</b></td>'
        f'<td align="right" style="color:{"#1e7f55" if (p["wow_pct"] or 0) >= 0 else "#c03434"}">{wow(p)}</td>'
        f'<td align="right" style="color:{col[p["status"]]}">{"n/a" if p["achieved_pct"] is None else fmt_pct(p["achieved_pct"])}</td></tr>'
        for p in m["people"])
    prods = "".join(
        f'<tr style="border-top:1px solid #e3e6ee"><td><b style="color:#3949ab">{i}</b> &nbsp;{e(t["name"])}</td>'
        f'<td align="right"><b>{fmt_vnd(t["revenue"])}</b> · {t["units"]:.0f} đơn vị</td></tr>'
        for i, t in enumerate(m["top_products_day"], 1))
    banner = (f'<tr><td align="center" bgcolor="#ffe08a" style="background-color:#ffe08a;color:#5a3d0a;font:700 12px Arial;padding:7px">'
              f'{e(banner_text)}</td></tr>' if banner_text else "")
    gap = m["gap_to_target"]
    gap_txt = f" · còn thiếu <b>{fmt_short(gap)}</b>" if gap and gap > 0 else ""
    target_txt = f" / {fmt_vnd(m['total_target'])}" if m["total_target"] else ""
    pct_txt = fmt_pct(abs(lw["pct"])) if lw["pct"] is not None else "n/a"
    ach_txt = fmt_pct(m["achieved_pct"]) if m["achieved_pct"] is not None else "n/a"
    html = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#eceef3" '
        "style=\"background-color:#eceef3;font-family:'Segoe UI',Roboto,Arial,sans-serif;color:#262a41\"><tr>"
        '<td align="center" bgcolor="#eceef3" style="background-color:#eceef3;padding:18px 10px">'
        '<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">'
        f'{banner}<tr><td bgcolor="#1f1b5c" style="background-color:#1f1b5c;color:#ffffff;padding:24px 26px">'
        f'<div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#c5cae9;font-weight:700">{e(brand)} · Báo cáo doanh số</div>'
        f'<div style="font-size:13px;color:#d5dbe8;margin-top:14px">Doanh thu {e(m["period_title"])}</div>'
        f'<div style="font-size:40px;font-weight:800;line-height:1.15;margin:4px 0 8px;color:#ffffff">{fmt_vnd(m["day_revenue"])}</div>'
        f'<div style="font-size:13px;color:#e6ede9"><b style="color:{"#9be8c0" if up else "#ff9e9e"}">{"▲" if up else "▼"} {pct_txt}</b> '
        f'so với {e(lw["label"])} ({fmt_vnd(lw["revenue"])}) · {m["day_lines"]} dòng, {m["day_units"]:.0f} đơn vị</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;border-top:1px solid #4a4780"><tr>'
        f'<td style="padding-top:12px;font-size:11px;color:#c5cae9">LŨY KẾ THÁNG {m["month"][:2]}<div style="font-size:20px;font-weight:700;color:#ffffff">{fmt_short(m["mtd_revenue"])}</div></td>'
        f'<td style="padding-top:12px;font-size:11px;color:#c5cae9">ĐẠT MỤC TIÊU<div style="font-size:20px;font-weight:700;color:#ffffff">{ach_txt}</div></td>'
        f'<td style="padding-top:12px;font-size:11px;color:#c5cae9">TIẾN ĐỘ KỲ VỌNG<div style="font-size:20px;font-weight:700;color:#ffffff">{m["pace_pct"]:.0f}%</div></td>'
        '</tr></table></td></tr><tr><td height="12"></td></tr>'
        '<tr><td bgcolor="#ffffff" style="background-color:#ffffff;padding:16px 20px"><div style="font-size:16px;font-weight:700;color:#1f1b5c;margin-bottom:8px">Tiến độ mục tiêu tháng</div>'
        f'{_bar(m["achieved_pct"], STATUS_COLOR[m["target_status"]], None, 14)}'
        f'<div style="font-size:12px;color:#5b6078;margin-top:6px">Đã đạt {fmt_vnd(m["mtd_revenue"])}{target_txt} · tiến độ kỳ vọng ngày {m["days_elapsed"]}/{m["days_in_month"]}: '
        f'<b>{m["pace_pct"]:.0f}%</b>{gap_txt} · dự báo cuối tháng ≈ {fmt_short(m["projected_month_end"])}</div></td></tr><tr><td height="12"></td></tr>'
        '<tr><td bgcolor="#ffffff" style="background-color:#ffffff;padding:16px 20px"><div style="font-size:16px;font-weight:700;color:#1f1b5c;margin-bottom:8px">Doanh thu từng người</div>'
        '<table role="presentation" width="100%" cellpadding="7" cellspacing="0" style="font-size:13px;border-collapse:collapse">'
        '<tr style="color:#6b7089;font-size:11px;text-align:left"><td>NGƯỜI BÁN</td><td align="right">KỲ NÀY</td><td align="right">SO KỲ TRƯỚC</td><td align="right">ĐẠT MỤC TIÊU</td></tr>'
        f'{rows}</table></td></tr><tr><td height="12"></td></tr>'
        '<tr><td bgcolor="#ffffff" style="background-color:#ffffff;padding:16px 20px">'
        f'<div style="font-size:16px;font-weight:700;color:#1f1b5c;margin-bottom:8px">Top 3 sản phẩm trong {m["noun"]}</div>'
        f'<table role="presentation" width="100%" cellpadding="7" cellspacing="0" style="font-size:13px">{prods}</table></td></tr>'
        '<tr><td align="center" style="padding:14px 0 2px;font-size:11px;color:#8a8fa6">'
        + (f'<a href="{e(m["summary_sheet_url"])}" style="color:#3949ab;font-weight:700;">Mở bảng tổng hợp Google Sheets</a><br>' if m.get("summary_sheet_url") else "")
        + 'Tạo tự động bởi AI Agent báo cáo doanh số · số liệu tính bằng Python từ các file nguồn</td></tr>'
        '</table></td></tr></table>')
    return _gmail_safe(html)

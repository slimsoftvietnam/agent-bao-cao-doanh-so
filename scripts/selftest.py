#!/usr/bin/env python3
"""Kiểm thử tự động bằng dữ liệu mẫu (không cần kết nối Google). Chạy: python scripts/selftest.py"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_sample_data import PEOPLE, build, gen_rows  # noqa: E402
from sales_report.parsing import parse_date, parse_number  # noqa: E402
from sales_report.pipeline import run  # noqa: E402

CONFIG = HERE.parent / "config"
RD = dt.date(2026, 10, 21)
NOW = dt.datetime(2026, 10, 22, 8, 0)
fails = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def codes(res, sev="critical"):
    return {i["code"] for i in res["issues"] if i["severity"] == sev}


def scenario(name, mode="dry-run"):
    with tempfile.TemporaryDirectory() as t:
        inbox = Path(t) / "in"
        build(inbox, name)
        return run(inbox, Path(t) / "out", CONFIG, mode, RD, NOW)


# --- bộ chuyển đổi số / ngày
for raw, want in [("1.250.000đ", 1250000), ("1,250,000", 1250000), ("12,5", 12.5), ("1.250,75", 1250.75),
                  ("1,250.75", 1250.75), ("(500)", -500), ("N/A", None), ("", None), (42, 42), ("1.250", 1250)]:
    check(f"parse_number({raw!r})", parse_number(raw) == want, str(parse_number(raw)))
for raw, want in [("21/10/2026", dt.date(2026, 10, 21)), ("2026-10-21", dt.date(2026, 10, 21)),
                  ("5-3-26", dt.date(2026, 3, 5)), ("31/02/2026", None), (46316, dt.date(2026, 10, 21)), ("abc", None)]:
    check(f"parse_date({raw!r})", parse_date(raw) == want, str(parse_date(raw)))

# --- dữ liệu hợp lệ: 4 file, 4 cấu trúc
ok = scenario("ok")
check("ok: trạng thái ok", ok["status"] == "ok", str(ok["issues"]))
check("ok: đọc đủ 10 nguồn", len(ok["files"]) == 10)
m = ok["metrics"]
check("ok: có 10 người", len(m["people"]) == 10)
for pid, name in PEOPLE.items():  # đối chiếu độc lập: 10 người, 6 kiểu file/cấu trúc (xlsx, csv, chữ hoa, số dạng chữ...)
    want = sum(x["total"] for x in gen_rows(pid, dt.date(2026, 9, 14), RD) if x["date"] == RD)
    got = next(p["day_revenue"] for p in m["people"] if p["name"] == name)
    check(f"ok: doanh thu ngày của {name} khớp dữ liệu gốc", abs(want - got) < 1, f"{want} vs {got}")
check("ok: tổng người = tổng ngày", abs(sum(p["day_revenue"] for p in m["people"]) - m["day_revenue"]) < 1)
check("ok: top 3 sản phẩm", len(m["top_products_day"]) == 3 and
      m["top_products_day"][0]["revenue"] >= m["top_products_day"][2]["revenue"])
check("ok: so tuần trước", m["last_week"]["date"] == "2026-10-14" and m["last_week"]["pct"] is not None)
check("ok: tỷ lệ đạt mục tiêu", m["achieved_pct"] and abs(m["achieved_pct"] - m["mtd_revenue"] / m["total_target"] * 100) < 1e-6)
check("ok: dry-run không gửi gì", all(not a["send"] for a in ok["actions"]))
check("ok: dry-run không chạm nhóm", all("example.com" not in str(a.get("to")) or a["to"] == ["nguoi.phu.trach@example.com"]
                                          for a in ok["actions"]))
# đối chiếu độc lập với số trong file nguồn
import pandas as pd  # noqa: E402
with tempfile.TemporaryDirectory() as t:
    build(Path(t), "ok")
    an = pd.read_excel(Path(t) / "Doanh_so_An_T10.xlsx", header=3)
    an = an[pd.to_datetime(an["Ngày"], errors="coerce").dt.date == RD]
    an_rev = next(p["day_revenue"] for p in m["people"] if p["name"].endswith("An"))
    check("ok: doanh thu An khớp đối chiếu độc lập", abs(an["Thành tiền"].sum() - an_rev) < 1)

# --- báo cáo tương tác: dữ liệu nhúng phải khớp số Python; email có đính kèm
import json, re  # noqa: E402
with tempfile.TemporaryDirectory() as t:
    build(Path(t) / "in", "ok")
    r = run(Path(t) / "in", Path(t) / "out", CONFIG, "dry-run", RD, NOW)
    html = Path(r["outputs"]["report"]).read_text(encoding="utf-8")
    emb = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
    di = {d: i for i, d in enumerate(emb["dates"])}
    day = sum(x[4] for x in emb["rows"] if x[0] == di["2026-10-21"])
    mtd = sum(x[4] for x in emb["rows"] if emb["dates"][x[0]] >= "2026-10-01")
    check("dashboard: dữ liệu nhúng khớp doanh thu ngày", abs(day - r["metrics"]["day_revenue"]) < 1)
    check("dashboard: dữ liệu nhúng khớp lũy kế tháng", abs(mtd - r["metrics"]["mtd_revenue"]) < 1)
    check("dashboard: có bộ lọc + chi tiết người", 'id="presets"' in html and "openPerson" in html and "<dialog" in html)
    check("email: có file đính kèm báo cáo tương tác", r["actions"][0].get("attachments") == [r["outputs"]["report"], r["outputs"]["excel"]]
          and Path(r["outputs"]["email"]).exists())

# --- Excel tổng hợp 10 người
with tempfile.TemporaryDirectory() as t:
    build(Path(t) / "in", "ok")
    r = run(Path(t) / "in", Path(t) / "out", CONFIG, "dry-run", RD, NOW)
    from openpyxl import load_workbook
    wb = load_workbook(r["outputs"]["excel"])
    ws = wb["Theo người"]
    names = [ws.cell(row=i, column=2).value for i in range(5, 15)]
    check("excel: đủ 6 sheet", wb.sheetnames == ["Tổng quan", "Theo người", "Sản phẩm", "Theo ngày", "Giao dịch", "Ghi chú dữ liệu"])
    check("excel: 10 người + dòng TỔNG", sorted(names) == sorted(PEOPLE.values()) and ws.cell(row=15, column=2).value == "TỔNG")
    check("excel: tổng doanh thu ngày khớp", abs(ws.cell(row=15, column=3).value - r["metrics"]["day_revenue"]) < 1
          and abs(sum(ws.cell(row=i, column=3).value for i in range(5, 15)) - r["metrics"]["day_revenue"]) < 1)
    check("excel: đính kèm trong thư", r["outputs"]["excel"] in r["actions"][0]["attachments"])

# --- báo cáo TUẦN (lịch hằng tuần: gửi kết quả tuần trước)
WEEK_END = dt.date(2026, 10, 25)
with tempfile.TemporaryDirectory() as t:
    build(Path(t) / "in", "ok", WEEK_END)
    r = run(Path(t) / "in", Path(t) / "out", CONFIG, "dry-run", None, dt.datetime(2026, 10, 26, 8, 0), "weekly")
    mw = r["metrics"]
    check("tuần: ngày chạy thứ Hai -> kỳ Thứ Hai–Chủ Nhật tuần trước", r["kind"] == "week" and r["report_date"] == "2026-10-25"
          and mw["period_start"] == "2026-10-19" and r["status"] == "ok", str(r["issues"]))
    for pid, name in PEOPLE.items():
        want = sum(x["total"] for x in gen_rows(pid, dt.date(2026, 9, 14), WEEK_END) if dt.date(2026, 10, 19) <= x["date"] <= WEEK_END)
        got = next(p["day_revenue"] for p in mw["people"] if p["name"] == name)
        check(f"tuần: doanh thu của {name} khớp", abs(want - got) < 1, f"{want} vs {got}")
    prev_want = sum(x["total"] for pid in PEOPLE for x in gen_rows(pid, dt.date(2026, 9, 14), WEEK_END) if dt.date(2026, 10, 12) <= x["date"] <= dt.date(2026, 10, 18))
    check("tuần: so với tuần trước đúng", abs(mw["last_week"]["revenue"] - prev_want) < 1 and mw["last_week"]["label"] == "tuần trước")
    check("tuần: tiêu đề/zalo ghi rõ tuần", "Tuần 19/10" in r["actions"][0]["subject"] and "Tuần 19/10" in Path(r["outputs"]["zalo"]).read_text(encoding="utf-8"))
    html_w = Path(r["outputs"]["report"]).read_text(encoding="utf-8")
    check("tuần: dashboard mặc định kỳ tuần", '"kind":"week"' in html_w)
    r2 = None
    build(Path(t) / "in2", "missing", WEEK_END)
    r2 = run(Path(t) / "in2", Path(t) / "out2", CONFIG, "dry-run", None, dt.datetime(2026, 10, 26, 8, 0), "weekly")
    check("tuần: thiếu file -> giữ báo cáo", r2["status"] == "anomaly" and "missing_file" in codes(r2))

# --- thư gửi Gmail: không còn thuộc tính nền rút gọn mà Gmail bỏ; có bản rút gọn + hàng đợi Zalo
with tempfile.TemporaryDirectory() as t:
    build(Path(t) / "in", "ok")
    r = run(Path(t) / "in", Path(t) / "out", CONFIG, "test", RD, NOW)
    for key in ("email", "email_compact"):
        h = Path(r["outputs"][key]).read_text(encoding="utf-8")
        check(f"gmail-safe: {key} không dùng 'background:' rút gọn", "background:#" not in h and 'bgcolor="#1f1b5c"' in h)
    check("compact: nhỏ hơn 12KB", Path(r["outputs"]["email_compact"]).stat().st_size < 12000)
    check("zalo: có dòng hàng đợi dự phòng", r["zalo_queue_rows"] and r["zalo_queue_rows"][0][-1] == "pending")

# --- onboarding: ghi config từ câu trả lời, rồi chạy báo cáo tuần bằng chính config đó
import json as _json, os, shutil, subprocess  # noqa: E402
with tempfile.TemporaryDirectory() as t:
    cfgdir = Path(t) / "config"
    shutil.copytree(CONFIG, cfgdir)
    build(Path(t) / "files", "ok", WEEK_END)
    ans = {"brand": "Test Co", "frequency": "weekly", "weekday": "monday", "time": "08:00", "report_email": ["a@congty.vn"],
           "zalo_group": "Nhóm X", "sources": [{"owner": n, "local_path": str(Path(t) / "files" / f), "monthly_target": 100000000}
                                                for n, f in [("Nguyễn Văn An", "Doanh_so_An_T10.xlsx"), ("Lê Minh Chi", "DoanhSo_Chi_T10.xlsx"),
                                                             ("Bùi Ngọc Lan", "DoanhSo_Lan_T10.csv"), ("Đỗ Thu Nga", "Nga_DoanhSo_T10.xlsx")]]}
    (Path(t) / "ans.json").write_text(_json.dumps(ans, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, BCDS_CONFIG_DIR=str(cfgdir), PYTHONIOENCODING="utf-8")
    run_cli = lambda *a: subprocess.run([sys.executable, str(HERE / "onboard.py"), *a], env=env, capture_output=True, text=True, encoding="utf-8")
    ins = _json.loads(run_cli("inspect", str(Path(t) / "files" / "Nga_DoanhSo_T10.xlsx")).stdout)[0]
    check("onboard: nhận diện file cấu trúc lạ (tiêu đề IN HOA, số dạng chữ)", ins["ok"] and ins["rows"] > 100 and ins["columns_detected"])
    w = run_cli("write-config", str(Path(t) / "ans.json"))
    check("onboard: ghi config thành công", w.returncode == 0, w.stderr[-300:])
    sc = (cfgdir / "schedule.yaml").read_text(encoding="utf-8")
    check("onboard: lịch tuần sáng thứ Hai = cron UTC 0 1 * * 1", "cron_utc: 0 1 * * 1" in sc)
    d2 = run_cli("write-config", str(Path(t) / "ans.json"))
    ans2 = dict(ans, frequency="daily"); (Path(t) / "ans2.json").write_text(_json.dumps(ans2, ensure_ascii=False), encoding="utf-8")
    run_cli("write-config", str(Path(t) / "ans2.json"))
    check("onboard: lịch hằng ngày T2–T6 = cron UTC 0 1 * * 1,2,3,4,5", "cron_utc: 0 1 * * 1,2,3,4,5" in (cfgdir / "schedule.yaml").read_text(encoding="utf-8"))
    run_cli("write-config", str(Path(t) / "ans.json"))
    col = run_cli("collect", "--out", str(Path(t) / "inbox"))
    check("onboard: collect chép đủ 4 file", len(_json.loads(col.stdout)["copied"]) == 4)
    r = run(Path(t) / "inbox", Path(t) / "out", cfgdir, "live", None, dt.datetime(2026, 10, 26, 8, 0))
    check("onboard→chạy live bằng config mới (4 người, tuần, gửi a@congty.vn)", r["kind"] == "week" and len(r["metrics"]["people"]) == 4
          and r["actions"][0]["to"] == ["a@congty.vn"] and r["send_team_report"], str(r["issues"]))

# --- chạy không cần agent: tải link, hàng đợi Zalo, workflow, gửi thư (dựng)
import threading, http.server, functools  # noqa: E402
from fetch_sources import download, source_url  # noqa: E402
import zalo_queue  # noqa: E402
import send_mail  # noqa: E402
with tempfile.TemporaryDirectory() as t:
    build(Path(t) / "srv", "ok")
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(Path(t) / "srv"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (Path(t) / "dl").mkdir()
    got = download(f"http://127.0.0.1:{srv.server_address[1]}/Doanh_so_An_T10.xlsx", Path(t) / "dl", "x.xlsx")
    srv.shutdown(); srv.server_close()
    check("fetch: tải file qua URL", got.exists() and got.stat().st_size == (Path(t) / "srv" / "Doanh_so_An_T10.xlsx").stat().st_size)
    check("fetch: URL Drive và Sheets", source_url({"id": "a", "drive": {"file_id": "ABC"}})[0].endswith("id=ABC")
          and "gviz/tq" in source_url({"id": "b", "type": "gsheet", "gsheet": {"spreadsheet_id": "S", "sheet_name": "Chi tiết"}})[0]
          and source_url({"id": "c", "drive": {"folder_id": "F"}}) is None)
    build(Path(t) / "in", "ok")
    r = run(Path(t) / "in", Path(t) / "out", CONFIG, "test", RD, NOW)
    qf = Path(t) / "q.jsonl"
    added = zalo_queue.add_from_result(r["result_path"], qf)
    again = zalo_queue.add_from_result(r["result_path"], qf)
    check("hàng đợi Zalo: xếp 1 tin, không trùng", len(added) == 1 and again == [] and zalo_queue.load(qf)[0]["status"] == "pending")
    rows = zalo_queue.load(qf); rows[0]["status"] = "sent"; zalo_queue.save(rows, qf)
    check("hàng đợi Zalo: đánh dấu đã gửi", zalo_queue.load(qf)[0]["status"] == "sent")
    check("gửi thư: dựng thư kèm 2 file đính kèm (SMTP --check)", any("[check]" in x for x in send_mail.send_actions(r["result_path"], check=True)))
    msg = send_mail.build(r["actions"][0], "x@y.z")
    check("gửi thư: có file .xlsx và .html đính kèm", sorted(p.get_filename().rsplit(".", 1)[1] for p in msg.iter_attachments()) == ["html", "xlsx"])

# --- test mode: chỉ người phụ trách; live bị chặn khi còn email mẫu
test = scenario("ok", "test")
check("test: chỉ gửi người phụ trách", all(a["to"] == ["nguoi.phu.trach@example.com"] for a in test["actions"] if a["channel"] == "gmail"))
try:
    scenario("ok", "live")
    check("live: bị chặn khi còn email mẫu", False)
except ValueError:
    check("live: bị chặn khi còn email mẫu", True)

# --- các kịch bản bất thường: phải giữ báo cáo, chỉ cảnh báo chủ
expect = {
    "spike": "revenue_deviation", "drop": "revenue_deviation", "missing": "missing_file",
    "duplicate": "duplicate_file", "duplicate_renamed": "duplicate_file", "empty": "empty_file",
    "empty_day": "no_data_for_date", "bad_structure": "wrong_structure", "blanks": "missing_values",
    "corrupt": "wrong_structure",
}
for name, code in expect.items():
    r = scenario(name, "dry-run")
    check(f"{name}: phát hiện {code}", code in codes(r), str(sorted(codes(r))))
    check(f"{name}: giữ báo cáo + chỉ cảnh báo chủ",
          r["status"] == "anomaly" and not r["send_team_report"] and r["metrics"] is None and
          all(a["kind"] == "alert" and a.get("to", ["nguoi.phu.trach@example.com"]) == ["nguoi.phu.trach@example.com"]
              for a in r["actions"]))

# --- chốt chặn: dù bất thường, mode live (email giả đã thay) cũng không gửi nhóm
import shutil  # noqa: E402
with tempfile.TemporaryDirectory() as t:
    cfg2 = Path(t) / "cfg"
    shutil.copytree(CONFIG, cfg2)
    rec = cfg2 / "recipients.yaml"
    rec.write_text(rec.read_text(encoding="utf-8").replace("example.com", "congty.vn"), encoding="utf-8")
    inbox = Path(t) / "in"
    build(inbox, "missing")
    r = run(inbox, Path(t) / "out", cfg2, "live", RD, NOW)
    check("live+bất thường: chỉ 1 thư cảnh báo cho chủ", [a["to"] for a in r["actions"] if a["channel"] == "gmail"] == [["nguoi.phu.trach@congty.vn"]]
          and all(a["send"] for a in r["actions"]))
    build(inbox := Path(t) / "in2", "ok")
    r = run(inbox, Path(t) / "out2", cfg2, "live", RD, NOW)
    g = [a for a in r["actions"] if a["channel"] == "gmail"][0]
    check("live+hợp lệ: gửi nhóm + cc", r["send_team_report"] and "giam.doc@congty.vn" in g["to"] and g["cc"])

print(f"\n{'TẤT CẢ ĐẠT' if not fails else 'CÓ LỖI: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)

#!/usr/bin/env python3
"""Sinh dữ liệu mẫu: 10 người, 7 kiểu file (Excel 5 cấu trúc khác nhau + CSV; một số người dùng chung cấu trúc).

  python scripts/make_sample_data.py --out sample-data/inbox                  # dữ liệu hợp lệ
  python scripts/make_sample_data.py --out /tmp/x --scenario spike           # có lỗi cố ý

Kịch bản: ok | spike | drop | missing | duplicate | duplicate_renamed | empty | empty_day | bad_structure | blanks | corrupt
Dữ liệu cố định theo seed nên kết quả lặp lại được. Ngày báo cáo mặc định 2026-10-21 (thứ Tư).
"""
import argparse
import datetime as dt
import random
import shutil
import zlib
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

CATALOG = [  # (tên, giá, trọng số bán chạy)
    ("Sữa tươi Vinamilk 1L", 32000, 9), ("Mì Hảo Hảo thùng 30 gói", 115000, 7), ("Nước mắm Nam Ngư 500ml", 42000, 5),
    ("Dầu ăn Neptune 1L", 58000, 5), ("Gạo ST25 túi 5kg", 175000, 6), ("Cà phê G7 hộp 18 gói", 69000, 6),
    ("Bánh Oreo gói", 28000, 4), ("Nước suối Aquafina thùng 24 chai", 98000, 4), ("Bột giặt OMO 3kg", 190000, 3),
    ("Trà Lipton hộp 25 gói", 52000, 3),
]
PEOPLE = {"an": "Nguyễn Văn An", "binh": "Trần Thị Bình", "chi": "Lê Minh Chi", "dung": "Phạm Quốc Dũng",
          "hoa": "Võ Thị Hoa", "khoa": "Đặng Anh Khoa", "lan": "Bùi Ngọc Lan", "minh": "Hoàng Đức Minh",
          "nga": "Đỗ Thu Nga", "phuc": "Lý Hoàng Phúc"}
SCALE = {"an": 1.0, "binh": 1.15, "chi": 0.9, "dung": 1.25, "hoa": 1.05, "khoa": 0.95, "lan": 1.1,
         "minh": 1.2, "nga": 0.85, "phuc": 1.0}
HEAD_FILL = PatternFill("solid", fgColor="0F2A4A")
HEAD_FONT = Font(bold=True, color="FFFFFF")


def gen_rows(pid: str, start: dt.date, end: dt.date, seed: int = 2026):
    rnd = random.Random(f"{seed}-{pid}")
    rows, d = [], start
    while d <= end:
        if d.weekday() != 6:  # nghỉ Chủ Nhật
            lines = rnd.randint(8, 10)  # mỗi sản phẩm tối đa 1 dòng/ngày -> không có dòng trùng giả
            for name, price, _w in rnd.sample(CATALOG, lines):
                qty = max(1, round(6 * SCALE[pid] * rnd.uniform(0.75, 1.25) * (1.15 if d.weekday() == 5 else 1)))
                rows.append({"date": d, "product": name, "qty": qty, "price": price, "total": qty * price})
        d += dt.timedelta(days=1)
    return rows


def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(horizontal="center")


def write_an_style(path, rows, owner, sheet):
    """Cấu trúc A (An và Chi dùng chung): tiêu đề + 2 dòng mô tả phía trên, bảng bắt đầu ở dòng 4, không có cột người bán."""
    wb = Workbook(); ws = wb.active; ws.title = sheet
    ws["A1"] = f"BÁO CÁO BÁN HÀNG – {owner.upper()}"; ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Tháng 10/2026 · Đơn vị: VNĐ"
    for i, h in enumerate(["Ngày", "Sản phẩm", "Số lượng", "Đơn giá", "Thành tiền"], 1):
        ws.cell(row=4, column=i, value=h)
    style_header(ws, 4, 5)
    for r, x in enumerate(rows, 5):
        ws.cell(row=r, column=1, value=x["date"]).number_format = "DD/MM/YYYY"
        ws.cell(row=r, column=2, value=x["product"]); ws.cell(row=r, column=3, value=x["qty"])
        ws.cell(row=r, column=4, value=x["price"]).number_format = "#,##0"
        ws.cell(row=r, column=5, value=x["total"]).number_format = "#,##0"
    last = 5 + len(rows)
    ws.cell(row=last, column=2, value="Tổng cộng").font = Font(bold=True)
    ws.cell(row=last, column=5, value=sum(x["total"] for x in rows)).number_format = "#,##0"
    ws.column_dimensions["B"].width = 36
    wb.save(path)


def write_binh_style(path, rows, owner, headers=None):
    """Cấu trúc B: tiếng Anh, bảng bắt đầu dòng 1, có cột Salesperson, thứ tự cột khác."""
    wb = Workbook(); ws = wb.active; ws.title = "Sales"
    heads = headers or ["Date", "Salesperson", "Item", "Qty", "Unit Price", "Total"]
    for i, h in enumerate(heads, 1):
        ws.cell(row=1, column=i, value=h)
    style_header(ws, 1, len(heads))
    for r, x in enumerate(rows, 2):
        for c, v in enumerate([x["date"], owner, x["product"], x["qty"], x["price"], x["total"]], 1):
            ws.cell(row=r, column=c, value=v)
        ws.cell(row=r, column=1).number_format = "YYYY-MM-DD"
    ws.column_dimensions["C"].width = 36
    wb.save(path)


def write_dung_style(path, rows, owner, blank_ratio=0.0):
    """Cấu trúc C: 2 sheet (sheet 'Tổng quan' chỉ là chữ), ngày/tiền là văn bản ('21/10/2026', '1.250.000đ'), có dòng TỔNG."""
    wb = Workbook(); ov = wb.active; ov.title = "Tổng quan"
    ov["A1"] = f"Báo cáo tháng 10/2026 – {owner}"; ov["A3"] = "Xem chi tiết ở sheet 'Chi tiết'."
    ws = wb.create_sheet("Chi tiết")
    ws["A1"] = "DOANH SỐ CHI TIẾT"
    heads = ["STT", "Mã SP", "Tên hàng", "SL", "Giá bán", "Doanh thu", "Ngày bán", "Nhân viên"]
    for i, h in enumerate(heads, 1):
        ws.cell(row=2, column=i, value=h)
    style_header(ws, 2, len(heads))
    rnd = random.Random(7)
    for n, x in enumerate(rows, 1):
        r = n + 2
        blank = rnd.random() < blank_ratio
        money = lambda v: f"{v:,.0f}".replace(",", ".") + "đ"
        vals = [n, f"SP{zlib.crc32(x['product'].encode()) % 900 + 100}", x["product"], x["qty"],
                None if blank else money(x["price"]), None if blank else money(x["total"]),
                x["date"].strftime("%d/%m/%Y"), owner]
        for c, v in enumerate(vals, 1):
            ws.cell(row=r, column=c, value=v)
    last = len(rows) + 3
    ws.cell(row=last, column=3, value="TỔNG").font = Font(bold=True)
    ws.cell(row=last, column=6, value=sum(x["total"] for x in rows))
    ws.column_dimensions["C"].width = 36
    wb.save(path)


def write_nga_style(path, rows, owner):
    """Cấu trúc D: tiêu đề IN HOA ở dòng 2, cột 'NGÀY BÁN | TÊN HÀNG | SL | GIÁ BÁN | DOANH THU | NHÂN VIÊN', số lưu dạng văn bản có dấu phẩy."""
    wb = Workbook(); ws = wb.active; ws.title = "Data"
    ws["A1"] = f"Doanh số {owner}"
    heads = ["NGÀY BÁN", "TÊN HÀNG", "SL", "GIÁ BÁN", "DOANH THU", "NHÂN VIÊN"]
    for i, h in enumerate(heads, 1):
        ws.cell(row=2, column=i, value=h)
    style_header(ws, 2, len(heads))
    for r, x in enumerate(rows, 3):
        for c, v in enumerate([x["date"], x["product"], x["qty"], f"{x['price']:,}", f"{x['total']:,}", owner], 1):
            ws.cell(row=r, column=c, value=v)
        ws.cell(row=r, column=1).number_format = "DD/MM/YYYY"
    ws.column_dimensions["B"].width = 36
    wb.save(path)


def write_csv_style(path, rows, owner):
    """Cấu trúc E: file CSV (UTF-8 BOM), ngày dd/mm/yyyy dạng chữ, không có cột người bán."""
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Ngày", "Sản phẩm", "Số lượng", "Đơn giá", "Thành tiền"])
        for x in rows:
            w.writerow([x["date"].strftime("%d/%m/%Y"), x["product"], x["qty"], x["price"], x["total"]])


def build(out: Path, scenario: str = "ok", report_date=dt.date(2026, 10, 21), start=dt.date(2026, 9, 14)):
    out.mkdir(parents=True, exist_ok=True)
    data = {pid: gen_rows(pid, start, report_date) for pid in PEOPLE}

    def mutate(pid, fn):
        data[pid] = fn(data[pid])

    def scale_day(k):
        def f(rows):
            for x in rows:
                if x["date"] == report_date:
                    x["qty"] = max(1, round(x["qty"] * k)); x["total"] = x["qty"] * x["price"]
            return rows
        return f

    if scenario == "spike":
        for pid in PEOPLE:
            mutate(pid, scale_day(3.2))      # ngày báo cáo tăng vọt -> lệch >50%
    elif scenario == "drop":
        mutate("chi", lambda r: [x for x in r if not (x["date"] == report_date and r.index(x) % 4)])
    elif scenario == "empty_day":
        mutate("dung", lambda r: [x for x in r if x["date"] != report_date])
    elif scenario == "empty":
        data["chi"] = []

    files = {
        "an": ("Doanh_so_An_T10.xlsx", lambda p, r: write_an_style(p, r, PEOPLE["an"], "Doanh so T10")),
        "binh": ("Sales_Binh_Oct2026.xlsx", lambda p, r: write_binh_style(p, r, PEOPLE["binh"])),
        "chi": ("DoanhSo_Chi_T10.xlsx", lambda p, r: write_an_style(p, r, PEOPLE["chi"], "Chi_T10")),
        "dung": ("BaoCao_Dung_2026-10.xlsx",
                 lambda p, r: write_dung_style(p, r, PEOPLE["dung"], 0.30 if scenario == "blanks" else 0.0)),
    }
    files.update({
        "hoa": ("Doanh_so_Hoa_T10.xlsx", lambda p, r: write_an_style(p, r, PEOPLE["hoa"], "Hoa T10")),
        "khoa": ("Sales_Khoa_Oct2026.xlsx", lambda p, r: write_binh_style(p, r, PEOPLE["khoa"])),
        "lan": ("DoanhSo_Lan_T10.csv", lambda p, r: write_csv_style(p, r, PEOPLE["lan"])),
        "minh": ("BaoCao_Minh_2026-10.xlsx", lambda p, r: write_dung_style(p, r, PEOPLE["minh"])),
        "nga": ("Nga_DoanhSo_T10.xlsx", lambda p, r: write_nga_style(p, r, PEOPLE["nga"])),
        "phuc": ("Phuc_Sales_Oct.xlsx", lambda p, r: write_binh_style(
            p, r, PEOPLE["phuc"], headers=["Order Date", "Sales Rep", "Product", "Quantity", "Price", "Amount"])),
    })
    if scenario == "bad_structure":
        files["binh"] = (files["binh"][0], lambda p, r: write_binh_style(
            p, r, PEOPLE["binh"], headers=["Cột A", "Cột B", "Cột C", "Cột D", "Cột E", "Cột F"]))
    for pid, (fname, writer) in files.items():
        if scenario == "missing" and pid == "dung":
            continue
        writer(out / fname, data[pid])
    if scenario == "duplicate":
        shutil.copy(out / files["an"][0], out / "Doanh_so_An_T10 (1).xlsx")
    if scenario == "duplicate_renamed":   # cùng dữ liệu của An, nhưng người khác đặt tên là của Chi
        write_an_style(out / "DoanhSo_Chi_T10.xlsx", data["an"], PEOPLE["chi"], "Chi_T10")
    if scenario == "corrupt":
        (out / files["binh"][0]).write_bytes(b"day khong phai file excel")
    return sorted(p.name for p in out.iterdir())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenario", default="ok")
    ap.add_argument("--end", default="2026-10-21", help="ngày cuối của dữ liệu = ngày/tuần báo cáo (dùng 2026-10-25 cho mẫu báo cáo tuần)")
    a = ap.parse_args()
    for n in build(Path(a.out), a.scenario, dt.date.fromisoformat(a.end)):
        print(n)

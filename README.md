# Agent Báo cáo doanh số — skill `bao-cao-doanh-so` cho Claude Code

Agent đọc **file Excel doanh số của từng người** (cấu trúc khác nhau cũng được), tự nhận diện cột, gộp, tính, phát hiện bất thường, rồi gửi **báo cáo HTML tương tác + file Excel tổng hợp** qua Gmail và nhắn **nhóm Zalo**. Chạy tự động **hằng tuần (sáng thứ Hai, báo cáo tuần trước)** hoặc **hằng ngày (báo cáo ngày hôm trước)** trên đám mây, không cần mở máy.

Mọi con số do **Python** tính; Claude chỉ hỏi, lấy file, gửi thư/Zalo và đặt lịch. Dữ liệu bất thường **không bao giờ** được gửi cho nhóm: chỉ người phụ trách nhận cảnh báo riêng.

## Quy trình agent làm với bạn

1. **Hỏi thông tin đầu vào:** file Excel của từng người (đường dẫn hoặc link Drive/Sheets), email nhận báo cáo, nhóm Zalo, lịch chạy (ví dụ: *hằng tuần sáng thứ Hai 8h* hoặc *hằng ngày 8h T2–T6*).
2. **Tự phân tích:** nhận diện cột → gộp file → tính doanh thu kỳ, lũy kế tháng, đạt mục tiêu, so kỳ trước, top 3 sản phẩm, doanh thu từng người → kiểm tra bất thường → tạo báo cáo HTML (phong cách bảng điều khiển, có lọc kỳ và xem chi tiết từng người) + Excel tổng hợp.
3. **Gửi kết quả:** email cho bạn (kèm HTML + Excel) và nhóm Zalo. Lịch hằng tuần gửi **tuần trước**; hằng ngày gửi **ngày trước**. Chạy tự động được khi tắt máy; nếu Zalo không gửi được trên đám mây thì **bỏ qua Zalo**, xếp vào hàng đợi và **gửi bù khi bạn bật máy**.

## Cài đặt

**Yêu cầu:** [Claude Code](https://claude.com/claude-code), Python 3.10+, tài khoản Google (Drive, Sheets, Gmail), tài khoản Zalo (nếu gửi Zalo).

```bash
git clone https://github.com/slimsoftvietnam/agent-bao-cao-doanh-so ~/.claude/skills/bao-cao-doanh-so
pip install -r ~/.claude/skills/bao-cao-doanh-so/requirements.txt
```

Windows (PowerShell):

```powershell
git clone https://github.com/slimsoftvietnam/agent-bao-cao-doanh-so "$env:USERPROFILE\.claude\skills\bao-cao-doanh-so"
pip install -r "$env:USERPROFILE\.claude\skills\bao-cao-doanh-so\requirements.txt"
```

Bật connector **Gmail, Google Drive, Google Sheets** tại *claude.ai → Settings → Connectors*.

## Sử dụng

Mở Claude Code và gõ: `Thiết lập báo cáo doanh số` (hoặc `/bao-cao-doanh-so`). Agent sẽ hỏi lần lượt như mục "Quy trình" ở trên, chạy thử cho bạn xem, rồi đặt lịch.

Sau đó: `Chạy báo cáo doanh số` (chạy thử, không gửi gì) · `Chạy báo cáo doanh số live` (gửi thật) · `Gửi Zalo tồn đọng`.

Hướng dẫn chi tiết (đặt lịch đám mây, Zalo, cảnh báo): [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md). Quy trình agent làm theo: [SKILL.md](SKILL.md).

## Thử ngay không cần Google

```bash
cd ~/.claude/skills/bao-cao-doanh-so
python scripts/run_report.py --inbox sample-data/inbox --date 2026-10-21            # báo cáo ngày, 10 người
python scripts/run_report.py --inbox sample-data/inbox-weekly --frequency weekly --today 2026-10-26   # báo cáo tuần trước
```

Mở `out/<ngày>/report.html` (bản tương tác) và file Excel `Tong-hop-doanh-so-*.xlsx`. Mẫu có sẵn: [docs/mau-bao-cao.html](docs/mau-bao-cao.html), [docs/mau-tong-hop-doanh-so.xlsx](docs/mau-tong-hop-doanh-so.xlsx).

## Phát hiện bất thường (không gửi nhóm, chỉ báo người phụ trách)

Doanh thu lệch > 50% so với mốc (TB 4 tuần cùng thứ/cùng tuần) · dữ liệu trống · thiếu file · trùng file · sai cấu trúc hoặc file hỏng · người bán không có dòng nào trong kỳ · quá nhiều ô trống. Ngưỡng và mức độ chỉnh trong `config/alert_rules.yaml`.

## Cấu trúc

```
SKILL.md                 quy trình cho Claude (thiết lập → chạy → Zalo tồn đọng)
HUONG-DAN-SU-DUNG.md     hướng dẫn người dùng
config/                  sources.yaml · recipients.yaml · alert_rules.yaml · schedule.yaml (do onboard.py ghi)
scripts/                 run_report.py · onboard.py · send_mail.py · make_sample_data.py · selftest.py · sales_report/
references/              phong-cach-bao-cao.md (phong cách giao diện) · answers.example.json
sample-data/             inbox (ngày) · inbox-weekly (tuần): 10 người, 5 cấu trúc Excel + CSV
docs/                    bản mẫu báo cáo HTML, email, Excel
```

## Lưu ý

- Config chứa email của bạn: muốn lịch chạy trên đám mây thì đẩy config lên **repo riêng tư** của bạn (không dùng bản công khai này).
- Zalo trên đám mây thường không gửi được (không có Zalo Web đăng nhập) — đây là lý do có hàng đợi Zalo.
- Muốn đính kèm HTML + Excel trong email tự động, cần mật khẩu ứng dụng Gmail (`GMAIL_USER`, `GMAIL_APP_PASSWORD`); không có thì thư gửi bản rút gọn qua connector và không đính kèm.

Phát hành bởi SlimSoft · Khóa học AI Agent SlimAI.

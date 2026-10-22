# Hướng dẫn sử dụng — Agent Báo cáo doanh số

## 1. Chuẩn bị (5 phút)

1. Cài skill cho **Claude Code** hoặc **Codex** (xem [README](README.md)). Claude Code: bật 3 connector trong *claude.ai → Settings → Connectors*: **Gmail, Google Drive, Google Sheets**. Codex (hoặc không dùng connector): chuẩn bị *mật khẩu ứng dụng Gmail* (`GMAIL_USER`, `GMAIL_APP_PASSWORD`) và file nguồn ở máy hoặc link Drive chia sẻ công khai.
2. Gom sẵn: file Excel/CSV doanh số của **từng người** (mỗi người một file; file có thể khác cấu trúc), danh sách email nhận báo cáo, tên chính xác nhóm Zalo (nếu dùng).
3. Muốn lịch chạy khi **tắt máy**: tải các file lên **Google Drive** (một thư mục hoặc link từng file) hoặc dùng Google Sheets. File chỉ nằm trên máy thì chỉ chạy thử được.

## 2. Thiết lập — agent hỏi bạn những gì

Gõ `Thiết lập báo cáo doanh số`. Agent hỏi:

| Câu hỏi | Bạn trả lời |
|---|---|
| File Excel hoặc **link Google Sheet** của từng người (mỗi Sheet một nhân viên) | Đường dẫn file/thư mục hoặc link Drive/Sheets. Agent phân tích và báo lại cấu trúc từng file để bạn xác nhận tên người bán |
| Mục tiêu doanh số tháng | Mỗi người một số (có thể bỏ qua) |
| Link Google Sheet tổng hợp | Một Sheet cố định để ghi kết quả (có thể bỏ qua) |
| Email | Email nhận báo cáo · cc · email người phụ trách nhận **cảnh báo** khi dữ liệu bất thường |
| Nhóm Zalo | Tên chính xác nhóm (có thể bỏ qua) |
| Lịch chạy | *Hằng tuần sáng thứ Hai 8:00* → gửi báo cáo **tuần trước** · *Hằng ngày 8:00 T2–T6* → gửi báo cáo **ngày trước** · hoặc ngày/giờ khác |

Agent ghi cấu hình vào `config/`, **chạy thử** cho bạn xem báo cáo HTML + Excel, rồi hỏi có gửi thật ngay không, và cuối cùng đặt lịch.

Muốn tự điền: sửa `config/sources.yaml`, `config/recipients.yaml`, `config/schedule.yaml` (hoặc tạo `answers.json` theo `references/answers.example.json` rồi `python scripts/onboard.py write-config answers.json`).

### Google Sheet: mỗi nhân viên một Sheet + một Sheet tổng hợp

- **Đầu vào:** gửi cho agent link Google Sheet của từng nhân viên (mỗi Sheet = một người). Link **cố định** — agent lưu vào `config/sources.yaml` (`gsheet.spreadsheet_id`), lần sau không hỏi lại; chỉ cần nhân viên cập nhật nội dung Sheet. Sheet nhiều tab: mặc định đọc mọi tab có bảng; chỉ muốn tab nào thì khai `sheets: ["Doanh số"]`. Cấu trúc cột mỗi Sheet có thể khác nhau.
- **Đầu ra:** một Google Sheet tổng hợp cố định (`config/recipients.yaml › summary_sheet`). Mỗi kỳ agent ghi đè các tab *Tổng quan, Theo người, Sản phẩm, Theo ngày* và nối thêm một dòng vào tab *Lịch sử*. Link Sheet này có trong email, tin Zalo và báo cáo HTML. Dữ liệu bất thường, `dry-run` và `test` **không** ghi vào Sheet.
- **Quyền truy cập:**
  - Claude Code: connector Google Sheets của tài khoản bạn đọc/ghi được mọi Sheet bạn có quyền.
  - Codex/GitHub Actions: tạo *tài khoản dịch vụ* Google (bật Sheets API + Drive API), tải khoá JSON, lưu vào biến `GOOGLE_SERVICE_ACCOUNT_JSON` (hoặc GitHub Secret cùng tên), rồi **chia sẻ** từng Sheet nhân viên (quyền Xem) và Sheet tổng hợp (quyền Biên tập) cho email của tài khoản dịch vụ. Không có khoá thì chỉ đọc được Sheet chia sẻ *Bất kỳ ai có đường liên kết* và không ghi được Sheet tổng hợp.

## 3. Ba chế độ chạy

| Chế độ | Nói với Claude | Kết quả |
|---|---|---|
| `dry-run` (mặc định) | "Chạy báo cáo doanh số" | Đọc dữ liệu thật, tạo báo cáo trong `out/…`, **không gửi gì** |
| `test` | "…mode test" | Chỉ gửi bản `[TEST]` cho người phụ trách |
| `live` | "…mode live" | Dữ liệu hợp lệ → gửi nhóm; bất thường → chỉ cảnh báo người phụ trách |

Quy trình khuyên dùng: `dry-run` → `test` → `live`. Địa chỉ `@example.com` làm `live` tự từ chối chạy.

## 4. Đặt lịch chạy trên đám mây (không cần mở máy)

1. **Repo riêng tư:** config chứa email nên đẩy lên repo **riêng tư** của bạn (`git add config/ && git commit`, `gh repo create <tên> --private --source . --push`). Không dùng repo công khai.
2. **Routine:** vào *claude.ai/code/routines → New routine* (hoặc nhờ Claude: "đặt lịch cho báo cáo doanh số"), chọn repo riêng tư, bật connector Drive/Sheets/Gmail.
3. **Lịch:** nhập đúng giờ theo `config/schedule.yaml` (`cron_utc`, ví dụ sáng thứ Hai 8:00 giờ Việt Nam = `0 1 * * 1`; hằng ngày T2–T6 = `0 1 * * 1,2,3,4,5`). Kiểm tra giờ chạy kế tiếp trên màn hình xác nhận.
4. **Prompt:** dán `routine_prompt` trong `config/schedule.yaml`. Chạy *Run now* với `mode=dry-run` vài lần rồi đổi sang `mode=live`.
5. **Đính kèm file vào email (khuyến nghị):** tạo *Mật khẩu ứng dụng* cho Gmail, thêm biến môi trường `GMAIL_USER` và `GMAIL_APP_PASSWORD` vào môi trường của routine. Không có hai biến này, email vẫn gửi nhưng là bản rút gọn, không đính kèm HTML/Excel.

### 4b. Đặt lịch bằng GitHub Actions (Codex và mọi agent — không cần agent lúc chạy)

1. `python scripts/onboard.py make-workflow` tạo `.github/workflows/bao-cao-doanh-so.yml` theo `config/schedule.yaml`.
2. Đẩy repo **riêng tư** (có `config/` và workflow) lên GitHub; vào *Settings → Secrets and variables → Actions* thêm `GMAIL_USER`, `GMAIL_APP_PASSWORD`.
3. Vào tab *Actions → Báo cáo doanh số tự động → Run workflow* với `mode=dry-run` để thử, rồi để lịch chạy `live`.
4. Workflow chạy `scripts/auto_run.py`: tải file nguồn (link chia sẻ công khai trong `config/sources.yaml`) → tính → tạo báo cáo → gửi email SMTP kèm HTML + Excel → xếp tin Zalo vào `zalo-queue/pending.jsonl` (tự commit). Báo cáo cũng được lưu trong *Artifacts* 30 ngày.
5. Hạn chế: không đọc được file Drive riêng tư (cần connector Drive của Claude Code); GitHub có thể trễ vài phút so với giờ hẹn.

## 5. Zalo và hàng đợi

- Lần đầu dùng Zalo: mở `chat.zalo.me` trong Claude, **quét QR** bằng điện thoại (agent không đăng nhập thay bạn).
- Trên đám mây thường không có Zalo Web → agent **bỏ qua Zalo**, ghi tin vào Google Sheet `ZaloQueue` (trạng thái `pending`) và gửi email như bình thường.
- Hàng đợi dạng file: `zalo-queue/pending.jsonl` (`python scripts/zalo_queue.py list` / `mark-sent <id>`); dạng Sheet: tab `ZaloQueue`.
- Khi bạn **bật máy**, tác vụ cục bộ "Gửi Zalo tồn đọng" (hoặc bạn gõ `Gửi Zalo tồn đọng`) đọc hàng đợi, gửi vào đúng nhóm Zalo rồi đánh dấu `sent`.
- Tạo Sheet `ZaloQueue`: một Google Sheet trống bất kỳ, gửi link cho agent; agent ghi vào `config/recipients.yaml › zalo_queue`.

## 6. Khi dữ liệu bất thường

| Mã | Khi nào | Mặc định |
|---|---|---|
| `revenue_deviation` | Tổng hoặc từng người lệch > 50% so với TB 4 kỳ cùng thứ/cùng tuần | Chặn |
| `missing_file`, `duplicate_file` | Thiếu file; trùng file (giống hệt, cùng dữ liệu khác tên, hoặc >1 file/người) | Chặn |
| `empty_file`, `no_data_for_date` | File không có dòng dữ liệu; người bán không có dòng nào trong kỳ | Chặn |
| `wrong_structure` | File hỏng hoặc thiếu cột ngày/sản phẩm/doanh thu | Chặn |
| `missing_values` | > 10% dòng thiếu/không đọc được | Chặn |
| `revenue_mismatch`, `negative_values`, `duplicate_rows`, `future_dates`, `unexpected_file` | Lỗi nhẹ | Lưu ý trong báo cáo |

Khi có lỗi **Chặn**: nhóm **không** nhận báo cáo; người phụ trách nhận email (và Zalo cá nhân nếu có) kèm cách sửa. Chỉnh trong `config/alert_rules.yaml`.

## 7. File Excel đầu vào được hiểu thế nào

Mỗi sheet: quét 30 dòng đầu tìm dòng tiêu đề, nhận diện cột theo bảng tên đồng nghĩa trong `config/sources.yaml › columns` (không phân biệt hoa/thường/dấu; cột lạ chỉ cần thêm tên vào đó). Bỏ qua dòng tiêu đề trang, dòng trống, dòng "Tổng", sheet không có bảng. Hiểu số `1.250.000đ`, `1,250.50`, `12,5` và ngày `dd/mm/yyyy`, `yyyy-mm-dd`, số serial Excel; file `.csv` cũng được. File không có cột người bán → dùng tên người bán đã khai.

## 8. Báo cáo và Excel có gì

- **Báo cáo HTML tương tác** (`report.html`): các thẻ biểu đồ (cơ cấu doanh thu, lũy kế so với mục tiêu, doanh thu theo ngày, đồng hồ đạt mục tiêu, top 3 sản phẩm, xếp hạng); **nút lọc kỳ** (ngày/tuần/tháng/7/30 ngày/tuỳ chọn); **bấm vào từng người** để xem tổng quan, sản phẩm, theo ngày, giao dịch. Mở bằng trình duyệt.
- **Excel tổng hợp** (`Tong-hop-doanh-so-<ngày>.xlsx`): Tổng quan · Theo người · Sản phẩm · Theo ngày · Giao dịch · Ghi chú dữ liệu.
- **Email** và **tin Zalo** tóm tắt kỳ báo cáo.

## 9. Việc cần biết

- Kỳ báo cáo: *hằng tuần* = tuần Thứ Hai–Chủ Nhật gần nhất đã kết thúc; *hằng ngày* = ngày làm việc trước đó (thứ Hai báo cáo thứ Bảy; đổi trong `general.business_days`).
- Zalo không có API công khai cho nhóm cá nhân nên gửi qua trình duyệt; có thể thất bại khi trình duyệt/Zalo Web chưa đăng nhập — đó là lý do có hàng đợi.
- Phong cách giao diện đã chốt trong `references/phong-cach-bao-cao.md`.

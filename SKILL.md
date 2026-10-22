---
name: bao-cao-doanh-so
description: Agent báo cáo doanh số tự động. Lần đầu: hỏi người dùng các file Excel doanh số của từng người, email nhận báo cáo, nhóm Zalo và lịch chạy (hằng tuần sáng thứ Hai hoặc hằng ngày). Sau đó tự đọc/nhận diện cột/gộp nhiều file Excel khác cấu trúc, tính doanh thu kỳ, lũy kế tháng, đạt mục tiêu, so kỳ trước, top 3 sản phẩm, doanh thu từng người bằng Python; phát hiện bất thường (lệch >50%, dữ liệu trống, thiếu/trùng file, sai cấu trúc); tạo báo cáo HTML tương tác + Excel tổng hợp; gửi Gmail và nhóm Zalo; đặt lịch chạy trên đám mây không cần mở máy. Dùng khi người dùng nói "cài/thiết lập báo cáo doanh số", "gửi báo cáo doanh số", "chạy báo cáo tuần/ngày", "đặt lịch báo cáo", "báo cáo doanh thu từ file Excel của nhân viên", hoặc khi chạy theo lịch (routine), hoặc khi cần gửi Zalo tồn đọng.
---

# Báo cáo doanh số tự động

**Phân vai:** Python (`scripts/`) đọc, ghép, tính, phát hiện bất thường, dựng báo cáo và **quyết định ai được nhận**. Bạn (agent) hỏi người dùng, lấy file về, gửi thư/Zalo đúng theo `result.json`, đặt lịch. **Không tự tính số bằng suy luận, không sửa số liệu.**

Thư mục skill = thư mục gốc repo này. Mọi đường dẫn dưới đây tính từ đó. Cài đặt: `git clone https://github.com/slimsoftvietnam/agent-bao-cao-doanh-so ~/.claude/skills/bao-cao-doanh-so` rồi `pip install -r requirements.txt`.

## Quy tắc cứng
1. Dữ liệu bất thường (`status = anomaly`) → **không gửi cho nhóm**; chỉ cảnh báo riêng cho người phụ trách (`owner`). Python đã chặn sẵn trong `actions`; không thêm người nhận ngoài `actions`.
2. Chế độ mặc định là `dry-run` (không gửi gì). Chỉ `live` khi người dùng đồng ý rõ ràng hoặc prompt của lịch ghi `mode=live`. Email mẫu `@example.com` làm `live` tự từ chối.
3. Không nhập mật khẩu thay người dùng (Zalo quét QR, Google đăng nhập): dừng và nhờ người dùng tự làm.
4. Zalo lỗi **không** được làm hỏng email; xem "Hàng đợi Zalo".
5. Giao diện báo cáo theo `references/phong-cach-bao-cao.md` — không tự đổi bảng màu/bố cục.

## Chọn luồng
- `python scripts/onboard.py status` → `configured: false` hoặc người dùng muốn đổi nguồn/email/lịch → **Luồng A (Thiết lập)**.
- Yêu cầu "chạy/gửi báo cáo" hoặc lịch tự động → **Luồng B (Chạy báo cáo)**.
- Máy người dùng bật và có hàng đợi Zalo, hoặc người dùng nói "gửi Zalo tồn đọng" → **Luồng C**.

---

## Luồng A — Thiết lập lần đầu (hỏi → ghi cấu hình → chạy thử → đặt lịch)

### A1. Hỏi thông tin đầu vào
Hỏi bằng AskUserQuestion (gom thành 1–2 lượt, ngôn ngữ đơn giản). Không bịa giá trị thiếu.

1. **File Excel doanh số của từng người** — đường dẫn file/thư mục trên máy *hoặc* link Google Drive / Google Sheets. Có thể một thư mục chứa nhiều file. Cho phép cấu trúc file khác nhau.
   - Chạy `python scripts/onboard.py inspect <file hoặc thư mục>…` rồi **trình bày bảng**: file → cấu trúc nhận diện (cột nào là ngày/sản phẩm/số lượng/đơn giá/thành tiền), số dòng, khoảng ngày, tên người đề xuất. Cho người dùng xác nhận/sửa **tên người bán**; file lỗi (`ok:false`) thì nêu lý do và hỏi lại.
   - Hỏi (không bắt buộc) **mục tiêu doanh số tháng** của từng người.
   - **Lưu ý đặt lịch không cần mở máy:** file phải nằm trên Google Drive/Sheets. Nếu người dùng chỉ có file trên máy: dùng cho lần chạy thử ngay, và hướng dẫn tải lên Drive rồi gửi link để lịch tự động đọc được (hoặc chọn chạy lịch trên máy).
2. **Email**: (a) email nhận báo cáo (một hoặc nhiều), (b) cc nếu có, (c) email người phụ trách nhận cảnh báo dữ liệu (mặc định = email đầu tiên).
3. **Nhóm Zalo** nhận báo cáo — tên chính xác nhóm (có thể bỏ qua). Hỏi thêm tên hội thoại cá nhân của người phụ trách nếu muốn nhận cảnh báo qua Zalo.
4. **Lịch chạy** — đưa lựa chọn có ví dụ:
   - *Hằng tuần, sáng thứ Hai 8:00* → gửi **báo cáo tuần trước** (Thứ Hai–Chủ Nhật vừa qua).
   - *Hằng ngày, 8:00 từ thứ Hai đến thứ Sáu* → gửi **báo cáo ngày hôm trước** (thứ Hai báo cáo thứ Bảy).
   - Khác (ngày/giờ khác) → ghi `weekday`/`days`/`time`. Múi giờ mặc định Asia/Ho_Chi_Minh.

### A2. Ghi cấu hình
Ghi `answers.json` (mẫu: `references/answers.example.json`) rồi chạy
```bash
python scripts/onboard.py write-config answers.json
```
Lệnh ghi `config/sources.yaml`, `config/recipients.yaml`, `config/schedule.yaml` (có `cron_utc` và `routine_prompt`). Đọc lại tóm tắt cho người dùng xác nhận.

### A3. Kết nối dịch vụ
Kiểm tra connector **Gmail, Google Drive, Google Sheets** đã bật cho phiên (nếu chưa: hướng dẫn *claude.ai → Settings → Connectors*). Zalo: mở `chat.zalo.me` bằng trình duyệt trong app, người dùng quét QR một lần.
Khuyến nghị: tạo *mật khẩu ứng dụng Gmail* để đính kèm file HTML + Excel vào thư (connector Gmail không đính kèm được file lớn); lưu thành `GMAIL_USER` và `GMAIL_APP_PASSWORD` (biến môi trường của routine đám mây). Không ghi mật khẩu vào file trong repo.

### A4. Chạy thử đầu tiên và gửi kết quả
1. Lấy file (Luồng B bước 1; file cục bộ: `python scripts/onboard.py collect --out inbox`).
2. `python scripts/run_report.py --inbox inbox --mode dry-run` (kỳ báo cáo gần nhất theo lịch đã chọn).
3. Mở `out/<ngày>/report.html` và Excel tổng hợp cho người dùng xem; nêu cảnh báo nếu có.
4. Hỏi **"Gửi thật cho các email này và nhóm Zalo bây giờ?"**. Đồng ý → `--mode live` và làm Luồng B bước 3–5. Chưa muốn → dừng.

### A5. Đặt lịch chạy tự động (không cần mở máy)
1. **Repo riêng tư chứa config:** config chứa email người dùng nên phải để repo **riêng tư**. Bản clone công khai không dùng được cho routine. Tạo repo riêng tư (vd. `gh repo create <tên> --private --source . --push` sau khi `git add config/`), hoặc hướng dẫn người dùng tạo trên GitHub.
2. **Routine đám mây:** dùng skill `schedule` (hoặc claude.ai/code/routines) tạo routine trên repo đó với cron trong `config/schedule.yaml` (`cron_utc`; hiển thị lại giờ chạy kế tiếp để người dùng kiểm tra), prompt = `routine_prompt`, connectors Drive/Sheets/Gmail và biến `GMAIL_USER`/`GMAIL_APP_PASSWORD` nếu có. Bấm *Run now* một lần để kiểm tra (đặt `mode=dry-run` trong lần thử).
3. **Hàng đợi Zalo:** nhờ người dùng tạo một Google Sheet trống tên "ZaloQueue" (hoặc tạo bằng connector nếu hỗ trợ) và gửi link; ghi vào `recipients.yaml › zalo_queue`. Rồi đặt **tác vụ trên máy** (công cụ scheduled-tasks, mỗi giờ trong giờ hành chính hoặc khi mở máy) chạy Luồng C.
4. Nói rõ với người dùng: email chạy được khi tắt máy; Zalo trên đám mây thường không gửi được (không có Zalo Web đăng nhập) nên được xếp hàng và tự gửi khi họ bật máy.

---

## Luồng B — Chạy báo cáo (theo lịch hoặc theo yêu cầu)

Chế độ: `dry-run` (mặc định khi người dùng tự yêu cầu) | `test` (chỉ gửi người phụ trách) | `live`. Tần suất lấy từ `config/schedule.yaml` (`frequency`): **weekly → báo cáo tuần trước; daily → báo cáo ngày làm việc trước đó**.

### 1. Lấy dữ liệu vào `inbox/` (thư mục mới/rỗng)
Với mỗi nguồn trong `config/sources.yaml`:
- `type: file` → connector **Google Drive**: tìm theo `drive.file_id` hoặc trong `drive.folder_id` với tên chứa `drive.name_contains`, tải về `inbox/` **giữ nguyên tên**. Nhiều file khớp → tải hết (Python sẽ báo trùng).
- `type: gsheet` → connector **Google Sheets** (`get_values`) → ghi `inbox/<id>.csv`, dòng đầu là tiêu đề.
- Chạy trên máy người dùng và có `local_path` → `python scripts/onboard.py collect --out inbox`.
- Không có file → **không tạo file giả**; Python sẽ báo `missing_file`. Connector lỗi/hết quyền → làm mục "Lỗi hạ tầng".

### 2. Chạy Python
```bash
pip install -q -r requirements.txt
python scripts/run_report.py --inbox inbox --mode <dry-run|test|live>
```
(`--frequency weekly|daily` ghi đè config; `--date YYYY-MM-DD` chọn ngày/tuần báo cáo.) Đọc `out/<ngày kết thúc kỳ>/result.json`: `status`, `kind`, `issues`, `metrics`, `actions`, `outputs`, `smtp_available`, `zalo_queue_rows`.

### 3. Gửi Gmail (mọi `actions` có `channel: gmail`, `send: true`)
- Có `smtp_available: true` → `python scripts/send_mail.py out/<ngày>/result.json` (gửi nguyên văn `email.html`, **đính kèm báo cáo tương tác `.html` và Excel tổng hợp**).
- Ngược lại → connector Gmail `send_message` với `body_compact_file` (`email_compact.html`, đọc nguyên văn) làm `htmlBody`; **nói rõ với người dùng rằng file đính kèm chưa gửi được** và gợi ý bật SMTP (A3).
- Dùng đúng `to`, `cc`, `subject`. Cảnh báo (`kind: alert`) → `alert.html`.

### 4. Gửi Zalo (action `channel: zalo`, `send: true`)
Trình duyệt trong app: mở `https://chat.zalo.me`. Gặp QR/đăng nhập, không có trình duyệt, hoặc lỗi bất kỳ → **bỏ qua Zalo, không báo lỗi toàn bộ**, chuyển sang "Hàng đợi Zalo". Nếu vào được: tìm đúng hội thoại `target`, **xác nhận tiêu đề trước khi gõ**, nhập nội dung `text_file` (gõ từng dòng với Shift+Enter, rồi **đối chiếu lại từng dòng** — từng có trường hợp rơi dòng; thiếu thì gửi bù), gửi, xác nhận tin hiện "Đã gửi".

### Hàng đợi Zalo
Zalo chưa gửi được → connector Sheets `append_values` ghi các dòng `zalo_queue_rows` (thời điểm · kỳ · tiêu đề · hội thoại · nội dung · `pending`) vào Sheet `recipients.yaml › zalo_queue` (sheet `ZaloQueue`). Nếu chưa cấu hình hàng đợi, báo người dùng gửi tay nội dung `zalo_report.txt`.

### 5. Nhật ký và báo lại
`recipients.yaml › audit_log.enabled` và mode ≠ dry-run → `append_values` dòng `audit_row`. Trả lời ngắn: kỳ báo cáo, chế độ, trạng thái, số vấn đề (nêu tiêu đề từng vấn đề nghiêm trọng), việc **đã gửi** và **đã bỏ qua/xếp hàng** (Zalo), nơi xem `out/<ngày>/report.html`.

### Lỗi hạ tầng (không có `result.json`)
Gửi **một** thư ngắn tới `owner.email` (mode ≠ dry-run) nêu bước lỗi và thông báo lỗi nguyên văn. Không gửi gì cho nhóm.

---

## Luồng C — Gửi Zalo tồn đọng (chạy khi máy người dùng bật)
1. Đọc Sheet hàng đợi (`recipients.yaml › zalo_queue`), lấy các dòng `status = pending`. Không có → kết thúc im lặng.
2. Mở `chat.zalo.me`. Chưa đăng nhập → nhờ người dùng quét QR (không tự đăng nhập), giữ nguyên `pending`, kết thúc.
3. Với từng dòng: xác nhận đúng hội thoại, gửi nội dung, đối chiếu từng dòng, rồi cập nhật dòng đó `status = sent` + thời điểm gửi (`update_values`). Gửi theo thứ tự thời gian, không gửi trùng.
4. Báo lại số tin đã gửi/còn lại.

## Mẫu dữ liệu & kiểm thử
- `sample-data/inbox` (10 người, 5 cấu trúc Excel + CSV, đến 21/10/2026) và `sample-data/inbox-weekly` (đến 25/10/2026, dùng `--frequency weekly`).
- Tạo lỗi cố ý: `python scripts/make_sample_data.py --out <thư mục> --scenario <spike|drop|missing|duplicate|duplicate_renamed|empty|empty_day|bad_structure|blanks|corrupt> [--end 2026-10-25]`.
- `python scripts/selftest.py` chỉ chạy khi người dùng yêu cầu.
- Cấu hình: `config/sources.yaml` (nguồn, mục tiêu, tên cột đồng nghĩa), `config/recipients.yaml`, `config/alert_rules.yaml` (ngưỡng 50%…), `config/schedule.yaml`. Hướng dẫn người dùng: `HUONG-DAN-SU-DUNG.md`.

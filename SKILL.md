---
name: bao-cao-doanh-so
description: Agent báo cáo doanh số tự động. Lần đầu: hỏi người dùng các file Excel doanh số của từng người, email nhận báo cáo, nhóm Zalo và lịch chạy (hằng tuần sáng thứ Hai hoặc hằng ngày). Sau đó tự đọc/nhận diện cột/gộp nhiều file Excel khác cấu trúc, tính doanh thu kỳ, lũy kế tháng, đạt mục tiêu, so kỳ trước, top 3 sản phẩm, doanh thu từng người bằng Python; phát hiện bất thường (lệch >50%, dữ liệu trống, thiếu/trùng file, sai cấu trúc); tạo báo cáo HTML tương tác + Excel tổng hợp; gửi Gmail và nhóm Zalo; đặt lịch chạy trên đám mây không cần mở máy. Chạy được trong Claude Code và Codex (và agent khác đọc SKILL.md). Dùng khi người dùng nói "cài/thiết lập báo cáo doanh số", "gửi báo cáo doanh số", "chạy báo cáo tuần/ngày", "đặt lịch báo cáo", "báo cáo doanh thu từ file Excel của nhân viên", hoặc khi chạy theo lịch (routine), hoặc khi cần gửi Zalo tồn đọng.
---

# Báo cáo doanh số tự động

**Phân vai:** Python (`scripts/`) đọc, ghép, tính, phát hiện bất thường, dựng báo cáo và **quyết định ai được nhận**. Bạn (agent) hỏi người dùng, lấy file về, gửi thư/Zalo đúng theo `result.json`, đặt lịch. **Không tự tính số bằng suy luận, không sửa số liệu.**

Thư mục skill = thư mục gốc repo này. Mọi đường dẫn dưới đây tính từ đó. Cài đặt rồi `pip install -r requirements.txt`:
- **Claude Code:** `git clone https://github.com/slimsoftvietnam/agent-bao-cao-doanh-so ~/.claude/skills/bao-cao-doanh-so` — gọi bằng `/bao-cao-doanh-so`.
- **Codex:** `git clone … "${CODEX_HOME:-$HOME/.codex}/skills/bao-cao-doanh-so"` (hoặc `<dự án>/.agents/skills/bao-cao-doanh-so`) — gọi bằng `$bao-cao-doanh-so`. Có sẵn `agents/openai.yaml` cho giao diện Codex.

## Công cụ theo từng agent (đọc trước)
Skill chỉ cần: chạy lệnh Python, hỏi người dùng, (tuỳ chọn) connector/MCP Gmail–Drive–Sheets, (tuỳ chọn) trình duyệt cho Zalo. Chọn đường **có sẵn** trong host của bạn:

| Việc | Claude Code | Codex / agent khác |
|---|---|---|
| Hỏi người dùng | AskUserQuestion | hỏi thẳng trong chat, gom 1–2 lượt |
| Lấy file nguồn | connector Google Drive/Sheets, hoặc `scripts/fetch_sources.py` | file cục bộ, hoặc link chia sẻ công khai qua `scripts/fetch_sources.py`, hoặc MCP Drive nếu host có |
| Gửi email (kèm HTML + Excel) | SMTP `scripts/send_mail.py` (ưu tiên), hoặc connector Gmail (bản rút gọn) | SMTP `scripts/send_mail.py` (cần `GMAIL_USER`, `GMAIL_APP_PASSWORD`); hoặc MCP Gmail nếu host có |
| Zalo | trình duyệt trong app / Claude in Chrome | trình duyệt/computer-use của host; không có → xếp hàng `zalo-queue/pending.jsonl` |
| Đặt lịch không cần mở máy | routine đám mây (skill `schedule`) **hoặc** GitHub Actions | **GitHub Actions** (`scripts/onboard.py make-workflow`); không cần agent |


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
Hỏi người dùng (AskUserQuestion trong Claude Code; hỏi thẳng trong chat với Codex) — gom thành 1–2 lượt, ngôn ngữ đơn giản. Không bịa giá trị thiếu.

1. **File Excel doanh số của từng người** — đường dẫn file/thư mục trên máy *hoặc* link Google Drive / Google Sheets. Có thể một thư mục chứa nhiều file. Cho phép cấu trúc file khác nhau.
   - Chạy `python scripts/onboard.py inspect <file hoặc thư mục>…` rồi **trình bày bảng**: file → cấu trúc nhận diện (cột nào là ngày/sản phẩm/số lượng/đơn giá/thành tiền), số dòng, khoảng ngày, tên người đề xuất. Cho người dùng xác nhận/sửa **tên người bán**; file lỗi (`ok:false`) thì nêu lý do và hỏi lại.
   - Hỏi (không bắt buộc) **mục tiêu doanh số tháng** của từng người.
   - **Lưu ý đặt lịch không cần mở máy:** file phải nằm trên Google Drive/Sheets (GitHub Actions/`fetch_sources.py` chỉ tải được link chia sẻ *Bất kỳ ai có đường liên kết*; file riêng tư cần connector Drive của Claude Code). Nếu người dùng chỉ có file trên máy: dùng cho lần chạy thử ngay, và hướng dẫn tải lên Drive rồi gửi link để lịch tự động đọc được (hoặc chọn chạy lịch trên máy).
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
Nếu host có connector/MCP **Gmail, Google Drive, Google Sheets** (Claude Code: *claude.ai → Settings → Connectors*) thì kiểm tra đã bật; nếu không có (thường gặp ở Codex) dùng SMTP + link công khai như bảng trên. Zalo: mở `chat.zalo.me` bằng trình duyệt trong app, người dùng quét QR một lần.
Khuyến nghị (bắt buộc với GitHub Actions/Codex): tạo *mật khẩu ứng dụng Gmail* để đính kèm file HTML + Excel vào thư (connector Gmail không đính kèm được file lớn); lưu thành `GMAIL_USER` và `GMAIL_APP_PASSWORD` (biến môi trường của routine, hoặc *GitHub Secrets*). Không ghi mật khẩu vào file trong repo.

### A4. Chạy thử đầu tiên và gửi kết quả
1. Lấy file (Luồng B bước 1; file cục bộ: `python scripts/onboard.py collect --out inbox`).
2. `python scripts/run_report.py --inbox inbox --mode dry-run` (kỳ báo cáo gần nhất theo lịch đã chọn).
3. Mở `out/<ngày>/report.html` và Excel tổng hợp cho người dùng xem; nêu cảnh báo nếu có.
4. Hỏi **"Gửi thật cho các email này và nhóm Zalo bây giờ?"**. Đồng ý → `--mode live` và làm Luồng B bước 3–5. Chưa muốn → dừng.

### A5. Đặt lịch chạy tự động (không cần mở máy)
Đọc `config/schedule.yaml` (`cron_utc`, `routine_prompt`). **Config chứa email người dùng → đặt trong repo RIÊNG TƯ** (`git add config/ && git commit`; vd. `gh repo create <tên> --private --source . --push`); bản clone công khai không dùng được cho lịch. Chọn một trong:

- **GitHub Actions (mọi agent, khuyến nghị cho Codex):** `python scripts/onboard.py make-workflow` tạo `.github/workflows/bao-cao-doanh-so.yml`; commit + push; thêm secrets `GMAIL_USER`, `GMAIL_APP_PASSWORD` (Settings → Secrets → Actions) rồi *Run workflow* với `mode=dry-run` để thử, sau đó chạy `live`. Chạy hoàn toàn bằng Python (`scripts/auto_run.py`): tải link công khai → tính → báo cáo → gửi email SMTP kèm file → xếp hàng Zalo. Hạn chế: chỉ tải được file chia sẻ công khai/`local` đã commit; GitHub có thể trễ vài phút.
- **Routine đám mây Claude Code:** dùng skill `schedule` (hoặc claude.ai/code/routines) trên repo riêng tư, cron `cron_utc`, prompt = `routine_prompt`, connectors Drive/Sheets/Gmail (+ `GMAIL_*` để đính kèm file). Hiển thị lại giờ chạy kế tiếp; *Run now* với `mode=dry-run` để kiểm tra. Đọc được file Drive riêng tư.
- **Codex:** dùng GitHub Actions ở trên; nếu bản Codex của người dùng có tính năng tự động hoá theo lịch thì có thể đặt `routine_prompt` ở đó (chỉ chạy khi máy bật).

**Hàng đợi Zalo:** tin Zalo không gửi được trong lần chạy tự động được xếp vào `zalo-queue/pending.jsonl` (GitHub Actions tự commit) hoặc Google Sheet "ZaloQueue" (khi chạy bằng connector; link ghi vào `recipients.yaml › zalo_queue`). Đặt **tác vụ trên máy** (scheduled task của host, mỗi giờ hoặc khi mở máy) chạy Luồng C.

Nói rõ với người dùng: email chạy được khi tắt máy; Zalo trên môi trường tự động thường không gửi được nên được xếp hàng và gửi bù khi họ bật máy.

---

## Luồng B — Chạy báo cáo (theo lịch hoặc theo yêu cầu)

Chế độ: `dry-run` (mặc định khi người dùng tự yêu cầu) | `test` (chỉ gửi người phụ trách) | `live`. Tần suất lấy từ `config/schedule.yaml` (`frequency`): **weekly → báo cáo tuần trước; daily → báo cáo ngày làm việc trước đó**.

### 1. Lấy dữ liệu vào `inbox/` (thư mục mới/rỗng)
Với mỗi nguồn trong `config/sources.yaml`:
- Không có connector/muốn không dùng agent: `python scripts/fetch_sources.py --out inbox` (link chia sẻ công khai; báo nguồn nào không tải được).
- `type: file` → connector **Google Drive** (nếu host có): tìm theo `drive.file_id` hoặc trong `drive.folder_id` với tên chứa `drive.name_contains`, tải về `inbox/` **giữ nguyên tên**. Nhiều file khớp → tải hết (Python sẽ báo trùng).
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
- Có `smtp_available: true` (đã có `GMAIL_USER`/`GMAIL_APP_PASSWORD`; luôn dùng được với Codex) → `python scripts/send_mail.py out/<ngày>/result.json` (gửi nguyên văn `email.html`, **đính kèm báo cáo tương tác `.html` và Excel tổng hợp**).
- Ngược lại, nếu host có connector Gmail → `send_message` với `body_compact_file` (`email_compact.html`, đọc nguyên văn) làm `htmlBody`; **nói rõ với người dùng rằng file đính kèm chưa gửi được** và gợi ý bật SMTP (A3).
- Dùng đúng `to`, `cc`, `subject`. Cảnh báo (`kind: alert`) → `alert.html`.

### 4. Gửi Zalo (action `channel: zalo`, `send: true`)
Trình duyệt trong app: mở `https://chat.zalo.me`. Gặp QR/đăng nhập, không có trình duyệt, hoặc lỗi bất kỳ → **bỏ qua Zalo, không báo lỗi toàn bộ**, chuyển sang "Hàng đợi Zalo". Nếu vào được: tìm đúng hội thoại `target`, **xác nhận tiêu đề trước khi gõ**, nhập nội dung `text_file` (gõ từng dòng với Shift+Enter, rồi **đối chiếu lại từng dòng** — từng có trường hợp rơi dòng; thiếu thì gửi bù), gửi, xác nhận tin hiện "Đã gửi".

### Hàng đợi Zalo
Zalo chưa gửi được → xếp hàng: `python scripts/zalo_queue.py add out/<ngày>/result.json` (file `zalo-queue/pending.jsonl`), hoặc nếu `recipients.yaml › zalo_queue` có Sheet: connector Sheets `append_values` các dòng `zalo_queue_rows` (thời điểm · kỳ · tiêu đề · hội thoại · nội dung · `pending`). Chưa cấu hình gì → báo người dùng gửi tay nội dung `zalo_report.txt`.

### 5. Nhật ký và báo lại
`recipients.yaml › audit_log.enabled` và mode ≠ dry-run → `append_values` dòng `audit_row`. Trả lời ngắn: kỳ báo cáo, chế độ, trạng thái, số vấn đề (nêu tiêu đề từng vấn đề nghiêm trọng), việc **đã gửi** và **đã bỏ qua/xếp hàng** (Zalo), nơi xem `out/<ngày>/report.html`.

### Lỗi hạ tầng (không có `result.json`)
Gửi **một** thư ngắn tới `owner.email` (mode ≠ dry-run) nêu bước lỗi và thông báo lỗi nguyên văn. Không gửi gì cho nhóm.

---

## Luồng C — Gửi Zalo tồn đọng (chạy khi máy người dùng bật)
1. Lấy hàng đợi: `git pull` rồi `python scripts/zalo_queue.py list` (file) và/hoặc đọc Sheet `ZaloQueue` các dòng `pending`. Không có → kết thúc im lặng.
2. Mở `chat.zalo.me` bằng trình duyệt của host. Chưa đăng nhập → nhờ người dùng quét QR (không tự đăng nhập), giữ `pending`, kết thúc.
3. Từng tin theo thứ tự thời gian: xác nhận đúng hội thoại, gửi nội dung, đối chiếu từng dòng, rồi đánh dấu: `python scripts/zalo_queue.py mark-sent <id>` (và/hoặc `update_values` trên Sheet). Sau cùng commit + push `zalo-queue/` nếu repo dùng GitHub Actions.
4. Báo lại số tin đã gửi/còn lại.

## Mẫu dữ liệu & kiểm thử
- `sample-data/inbox` (10 người, 5 cấu trúc Excel + CSV, đến 21/10/2026) và `sample-data/inbox-weekly` (đến 25/10/2026, dùng `--frequency weekly`).
- Tạo lỗi cố ý: `python scripts/make_sample_data.py --out <thư mục> --scenario <spike|drop|missing|duplicate|duplicate_renamed|empty|empty_day|bad_structure|blanks|corrupt> [--end 2026-10-25]`.
- `python scripts/selftest.py` chỉ chạy khi người dùng yêu cầu. Chạy tự động không agent: `python scripts/auto_run.py --mode dry-run`.
- Cấu hình: `config/sources.yaml` (nguồn, mục tiêu, tên cột đồng nghĩa), `config/recipients.yaml`, `config/alert_rules.yaml` (ngưỡng 50%…), `config/schedule.yaml`. Hướng dẫn người dùng: `HUONG-DAN-SU-DUNG.md`.

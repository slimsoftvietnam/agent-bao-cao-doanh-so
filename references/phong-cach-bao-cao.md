# Phong cách báo cáo (đã chốt với người dùng — giữ nguyên khi chỉnh sửa)

Phong cách tham khảo: bảng điều khiển gồm các thẻ trắng trên nền xám nhạt, tông xanh chàm, tiêu đề thẻ căn giữa (người dùng cung cấp ảnh mẫu; ảnh không đưa vào repo). **Học phong cách, không sao chép nội dung** — nội dung luôn là doanh số.
Người dùng đã từng chê hai bản trước là "xấu, khó đọc": bản gradient + chữ nhỏ dày đặc, và bản kem/cam giống trang CV Radar. Đừng quay lại hai kiểu đó.

Mã nguồn: `scripts/sales_report/dashboard_template.html` (báo cáo tương tác), `render.py` (email.html, email_compact.html, alert.html), `excel_export.py` (Excel).

## Nguyên tắc
1. **Một thẻ = một câu hỏi**, tiêu đề căn giữa, rõ ràng (vd. "Cơ cấu doanh thu theo người"). Ít chữ, nhiều biểu đồ và số lớn.
2. **Dễ đọc trước tiên**: cỡ chữ thân ≥ 14px, nhãn trục ≥ 11px, tương phản cao, không dùng chữ xám nhạt trên nền xám.
3. Nền xám nhạt, thẻ trắng bo góc nhỏ (6px), bóng rất nhẹ. Không gradient, không hiệu ứng rườm rà.
4. Màu **trạng thái** (xanh lá/vàng/đỏ) chỉ dùng để báo tiến độ và tăng/giảm; phần còn lại dùng dải xanh chàm.

## Token
| Vai trò | Giá trị |
|---|---|
| Nền trang | `#eceef3` |
| Thẻ | `#ffffff`, viền/đường kẻ `#e3e6ee` |
| Xanh chàm đậm (tiêu đề, số lớn, cột nổi bật) | `#1f1b5c` |
| Xanh chàm vừa / nhạt / rất nhạt | `#3949ab` / `#7986cb` / `#c5cae9` |
| Chữ / chữ phụ | `#262a41` / `#6b7089` |
| Tốt / cảnh báo nhẹ / xấu | `#2e9e6b` / `#e09a2b` / `#d64545` (nền nhạt: `#e1f5ec` / `#fcefd6` / `#fbe3e3`) |
| Bảng màu 10 người (biểu đồ tròn) | `#1f1b5c #3949ab #7986cb #b3bbe6 #00838f #4db6ac #f2a65a #e57373 #9575cd #8d6e63` |
| Font | Roboto (Google Fonts), dự phòng Segoe UI / system-ui |

## Bố cục báo cáo tương tác (lưới 3 cột, ≤960px còn 2, ≤620px còn 1)
- Thanh trên: tên báo cáo + ngày; **bộ lọc kỳ doanh thu** (Hôm nay · Tuần này · Tháng này · 7 ngày · 30 ngày · Tuỳ chọn từ–đến).
- Hàng 1–2: *Cơ cấu doanh thu theo người* (tròn + chú giải, cao 2 hàng) · *Lũy kế tháng so với mục tiêu* (đường + đường đứt cam = nhịp cần đạt) · *Doanh thu theo ngày* (cột, cột đậm = kỳ chọn) · *Đạt mục tiêu tháng* (đồng hồ nửa vòng + vạch nhịp cần đạt) · *Số lớn* (doanh thu kỳ, so tuần trước, TB/ngày).
- Hàng 3: *Top 3 sản phẩm* · *Xếp hạng từng người* (bảng rộng 2 cột, lọc theo tiến độ + sắp xếp).
- **Bấm vào người** (dòng bảng, mục chú giải hoặc miếng tròn) → hộp thoại chi tiết 4 tab: Tổng quan · Sản phẩm · Theo ngày · Giao dịch (có ô tìm kiếm).
- Mọi biểu đồ là SVG/CSS thuần, tự vẽ lại khi đổi bộ lọc; trang tự chứa (1 file) và in được.

## Email (`email.html`)
Bảng + CSS nội tuyến (Gmail không chạy JS/SVG): thẻ trắng trên nền `#eceef3`, khối đầu xanh chàm đậm với số doanh thu lớn, thanh tiến độ, danh sách người có chấm màu, top 3 sản phẩm, cột xu hướng. Luôn có dòng nhắc mở **file đính kèm** (báo cáo tương tác `.html` + Excel tổng hợp).

## Excel tổng hợp (`Tong-hop-doanh-so-<ngày>.xlsx`)
6 sheet: Tổng quan · Theo người (10 dòng + TỔNG, thanh dữ liệu cho % đạt, nhãn trạng thái tô màu) · Sản phẩm · Theo ngày (ma trận ngày × người) · Giao dịch (có bộ lọc) · Ghi chú dữ liệu. Tiêu đề bảng nền `#1f1b5c` chữ trắng, số định dạng `#,##0` và `0.0%`, cố định hàng đầu/cột tên. Giá trị ghi sẵn, không công thức.

## Khi chỉnh sửa
- Giữ đúng token và bố cục trên; thêm thẻ mới phải trả lời một câu hỏi cụ thể và dùng cùng kiểu tiêu đề.
- Sau khi sửa giao diện: chạy `run_report.py` rồi mở `out/<ngày>/report.html`, thử đổi bộ lọc và bấm một người; kiểm tra console không lỗi.
- Với 10 người trở lên, chú giải/bảng phải vẫn đọc được không cần cuộn ngang trên màn hình rộng.

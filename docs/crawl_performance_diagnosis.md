# Chẩn đoán tốc độ crawl và ảnh nguồn — 04/11/2026

## Quan sát trong phiên lỗi

- Ở mốc khoảng 409 giây: đã thấy 31 bình luận, giữ 16 ảnh, 15 bình luận có lỗi chụp.
- Kết thúc: giữ 19 ảnh trong 31 bình luận đã thấy; 12 bình luận chưa chụp được. Đây là bộ đếm của phiên cũ, không phải xác nhận rằng tất cả ảnh đều hợp lệ: kiểm tra trực tiếp phát hiện ảnh trắng trong thư viện.
- Lỗi cuối: `Locator.scroll_into_view_if_needed: Timeout 4000ms exceeded` đối với thẻ Threads đã rời DOM sau khi cuộn. Crawler trước đây đợi hết timeout dù locator không còn tồn tại; các lượt thử lại làm cộng dồn thời gian.
- Máy đồng thời chạy tác vụ FFmpeg trong công cụ chia video khác. Mẫu tải CPU toàn máy khoảng 43%; chưa có đo đạc để quy chính xác bao nhiêu độ trễ cho tác vụ này. Không tự dừng tác vụ đó.
- Không có benchmark cùng URL/cùng điều kiện của phiên trước, vì vậy chưa thể đưa ra tỷ lệ tăng/giảm tốc độ đáng tin cậy.

## Các sửa chữa

1. Phóng nội dung trang 125% thay vì kết hợp zoom trình duyệt gốc với vùng chụp CDP tùy chỉnh. Reset zoom gốc về 100%, giữ độ phân giải chụp 2×. Cách này tái sử dụng screenshot phần tử của Playwright, tránh vùng chụp bị sai trên trang cuộn/ảo hóa.
2. Kiểm tra locator còn tồn tại trước khi chờ scroll. Thẻ đã rời DOM được bỏ qua ngay trong lượt đó, có thể thử lại khi xuất hiện trong lượt đọc DOM sau; không coi là đã thu thập thành công.
3. Loại ảnh trống/gần đồng màu khỏi kết quả chụp; không công bố ảnh trắng là ảnh bình luận hợp lệ.
4. Tạo lại thư mục cache/assets khi cần sử dụng. Log HTTP 500 cho thấy đường dẫn `data/cache` bị thiếu khi tạo ảnh xem trước. API xem trước được kiểm tra lại trả HTTP 200 và PNG hợp lệ.

Giữ cơ chế chờ ảnh/poster tải xong và kiểm tra chữ thuộc đúng thẻ. Chưa đo được tốc độ crawl nguồn thật sau bản sửa; cần crawl lại để thay ảnh trắng của phiên cũ. Không xóa tự động dữ liệu đã lưu.

## Vì sao bài viết gốc không có ảnh chụp

`collector.py` hiện chụp các thẻ bình luận; bài gốc chỉ trả chữ và tên tác giả. `render.py` tạo cảnh mở đầu với trường ảnh trống, nên dựng lại thành thẻ chữ. Đây là chức năng chưa triển khai, không phải lỗi API giọng đọc hay quyền đăng nhập. Muốn giữ giao diện, ảnh/video đính kèm của bài gốc cần bổ sung bước định vị, screenshot và lưu ảnh riêng rồi truyền ảnh đó cho cảnh mở đầu.

## Cập nhật sau chẩn đoán

Đã bổ sung bước screenshot bài gốc trước khi cuộn bình luận. Ảnh được lưu vào `post_image` và bản sao trong project; render bắt buộc có ảnh thật, không dùng thẻ chữ thay thế. Meme xuất hiện ngay sau mở đầu khi bật meme. Các nhận định thiếu chức năng ở mục trước mô tả trạng thái trước bản sửa này. Kiểm tra tự động dùng fixture trình duyệt, chưa xác minh cấu trúc bài gốc trên mọi URL TikTok/Threads thật.

# Editor bốn bước

Triển khai lựa chọn A đã được duyệt: Nguồn, Kịch bản, Phong cách, Dựng.
Giữ HTML/CSS/JavaScript thuần, API và định dạng dự án hiện có.

- [x] Chia HTML thành bốn panel; preview cố định bên phải, xếp dọc trên mobile.
- [x] Thêm điều hướng, tóm tắt dựng và lỗi có đường dẫn về bước cần sửa.
- [x] Làm gọn bình luận, cấu hình giọng và nhãn; đồng bộ các màn phụ.
- [x] Kiểm thử Chrome với API giả lập ở 320, 390, 768, 1024 và 1440px; kiểm tra lưu/mở, chuyển bước, cấu hình dựng và hàng loạt.

11 test hiện có về giọng đọc và chọn bình luận chạy thành công. Chạy toàn bộ unittest bị kẹt khi Windows tạo socket trong asyncio (trước khi TestClient vào ứng dụng); chưa xác minh toàn bộ backend trong môi trường này.

Không gọi crawl/TTS trả phí trong kiểm thử. Không xóa dữ liệu hay tính năng đã có.

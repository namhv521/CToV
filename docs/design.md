# Thiết kế CommentCut

Ứng dụng chạy cục bộ để thư viện video nền không cần tải lên dịch vụ ngoài. FastAPI quản lý dự án JSON, tài sản và hàng đợi dựng tuần tự; FFmpeg xử lý video, Pillow tạo ảnh bình luận. Frontend dùng HTML/CSS/JavaScript thuần.

Luồng: link TikTok/Threads → trình duyệt Playwright đọc nội dung công khai và các phản hồi nhìn thấy/JSON phản hồi mạng → chuẩn hóa, loại trùng → người dùng chọn/sửa/sắp xếp → tổng hợp giọng → tính thời lượng thật → ghép ảnh và meme trên nền → MP4 + ảnh PNG + manifest timeline + phụ đề SRT. Crawler có giới hạn thời gian/số bình luận và luôn báo dữ liệu có thể chưa đầy đủ. Không vượt CAPTCHA hoặc xuất cookie từ trình duyệt cá nhân. Có browser profile riêng và lệnh đăng nhập tương tác.

Mỗi bình luận có văn bản hiển thị và lời đọc riêng, ảnh chụp thay thế tùy chọn, meme, âm thanh, thời gian meme. Nền được crop giữa 9:16, bỏ âm thanh gốc, lặp nếu ngắn, tiếp tục mốc thời gian giữa các cảnh. Giọng đọc được chuẩn hóa âm lượng. Meme được chèn giữa các bình luận, không chồng lên lời đọc. Có hiệu ứng âm thanh tổng hợp sẵn và ảnh chữ gốc để dùng thử; thay bằng tài sản của người dùng để đạt phong cách mẫu.

Google TTS miễn phí cần Internet và không có SLA. Edge TTS là lựa chọn phụ. ElevenLabs dùng API chính thức; Vbee gửi tác vụ và poll kết quả, không âm thầm đổi nhà cung cấp trả phí. API key chỉ lưu cục bộ khi người dùng bấm lưu, không xuất trong dự án/manifest/trả về API.

Dự án và trạng thái job ghi atomic xuống đĩa. Chỉ một tác vụ dựng chạy cùng lúc. Có hủy job, timeout subprocess, thông báo job gián đoạn sau khởi động lại. Render nhiều phần khi vượt thời lượng giới hạn, không cắt giữa câu. Bản dựng nhỏ dùng 360×640; xuất 720×1280 hoặc 1080×1920. Server chỉ nghe 127.0.0.1, chặn host/origin lạ, tài sản chỉ được truy cập bằng ID được quản lý.

Kiểm tra: xác thực URL và ID, trích xuất fixture TikTok/Threads và không lẫn bài đề xuất, lưu/mở dự án, nhập dữ liệu, upload tài sản, job hủy/lỗi, TTS miễn phí thực và FFmpeg xuất thực có audio/video. QA giao diện desktop/mobile.

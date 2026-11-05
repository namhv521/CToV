# Chụp bình luận thật và đọc giọng

## Chọn tối đa 120 bình luận nhiều tim

### Sửa lỗi chỉ lấy vài bình luận trên Threads

Threads dùng danh sách ảo hóa: khi cuộn, vị trí phần tử DOM bị tái sử dụng. Crawler tìm thẻ bằng permalink của từng bình luận rồi lấy thẻ cha gần nhất, thay vì dùng chỉ số thẻ toàn trang. Chụp theo thứ tự DOM giúp tránh cuộn qua lại làm phần tử chưa chụp bị loại khỏi DOM. Việc chọn top theo số tim vẫn diễn ra độc lập sau mỗi lần chụp.

Giao diện hiển thị tiến độ thực qua `/api/crawl-status`: số bình luận đã đọc, ảnh đang giữ, lỗi chụp và thời gian. Lỗi crawl thay thế thông báo đang chạy, tránh để dòng “Đang đọc…” sau khi tác vụ đã lỗi. Cửa sổ đăng nhập riêng dùng lại tab đầu tiên để không để lại tab trắng giữ profile khi người dùng đóng tab đăng nhập.

Mặc định giới hạn 120. Crawler tiếp tục tải bình luận, không dừng ngay khi gặp 120 bình luận đầu tiên. Trong lúc duyệt, giữ ảnh của nhóm nhiều tim nhất hiện có; bình luận nhiều tim xuất hiện về sau thay cho bình luận ít tim. Kết quả cuối xếp theo số tim giảm dần, tối đa 120; nếu đọc/chụp được ít hơn thì trả toàn bộ số đó. Tim chính xác từ JSON của đúng bình luận được ưu tiên khi có; nếu không, dùng số hiển thị trên thẻ, có thể được nền tảng rút gọn như 1.2K.

Ngừng khi không thấy bình luận mới sau nhiều lần cuộn, hoặc chạm thời gian 10 phút. Vì nền tảng có thể chặn/ẩn dữ liệu hoặc chỉ trả thứ tự cá nhân hóa, kết quả là top trong số bình luận truy cập và chụp được, không được gắn nhãn top tuyệt đối của toàn video khi chưa xác minh đọc hết. Giao diện báo số bình luận đã đọc, số ảnh giữ lại, lỗi chụp và tình trạng hết thời gian. Dự án và nhập JSON cùng hỗ trợ tối đa 120 bình luận.

Crawler mặc định chụp nguyên phần tử bình luận đang hiển thị trong Chrome, giữ avatar, tên, thời gian, chữ, biểu tượng, số tim và các nút nằm trong thẻ gốc. Không dựng lại hoặc giả số tim bằng Pillow. Số liệu là ảnh chụp tại thời điểm crawl, không phải dữ liệu cập nhật liên tục.

Chữ để tạo giọng được đọc từ chính phần tử đã chụp trong DOM, không dùng OCR khi nền tảng đã cung cấp văn bản. Cách này tránh lỗi nhận dạng dấu tiếng Việt, không đọc nhầm số tim hoặc chữ trên nút. Ảnh và chữ được lưu riêng nhưng cùng metadata nguồn/thời điểm. Không tự đọc chữ nằm trong ảnh đính kèm bên trong bình luận nếu nền tảng không có text tương ứng; OCR cho trường hợp đó chưa được triển khai.

Trong giao diện, bình luận crawl có ảnh gốc và thời điểm chụp; bấm ảnh để xem đầy đủ. Văn bản gốc được khóa để giữ khớp ảnh. Muốn phiên âm từ viết tắt hoặc đổi nhịp đọc, sửa **Lời đọc riêng**. Meme và âm thanh vẫn được chọn riêng cho từng bình luận.

Ảnh được lưu PNG ở device scale 2×, tải avatar trước khi chụp trong giới hạn thời gian, giữ tỷ lệ khi đưa vào video. Không crop mất nội dung để vừa khung. Ảnh rất dài sẽ thu nhỏ; nên chọn bình luận vừa phải và xuất 720p/1080p để đọc rõ.

Đối với ảnh chụp, lựa chọn ẩn tên trong ảnh dựng không thể sửa tên/avatar đã nằm trong pixel. Không coi lựa chọn đó là công cụ ẩn danh ảnh chụp. Người dùng cần tự che thông tin trong ảnh nếu muốn trước khi nhập lại.

Crawler chỉ đóng hộp thoại bằng nút Đóng hoặc Escape theo thao tác bình thường. Không ẩn hộp đăng nhập bằng CSS, không vượt CAPTCHA. Thẻ đang bị che, phần tử thay nội dung, ảnh hỏng hoặc bình luận vượt 1500 ký tự sẽ không được trả lại như ảnh thành công. Giao diện báo số ảnh thành công và lỗi gần nhất. Không chuyển âm thầm sang ảnh bình luận giả. Nội dung nhập thủ công vẫn có thể dùng ảnh dựng hoặc ảnh do người dùng tải lên.

Threads đọc các thẻ trong cột của bài gốc và dừng trước mục Related threads khi có. TikTok dùng phần tử comment-item nếu nền tảng cho hiển thị. Cần đăng nhập riêng khi trang yêu cầu. Giao diện nền tảng có thể thay đổi; không cam kết lấy được toàn bộ bình luận từ mọi link.

Các tệp liên quan: `capture.py`, `collector.py`, `threads_dom.js`, model `Comment`, giao diện `static/app.js` và nhánh ảnh trong `render.py`. Metadata ảnh giữ `role=comment_capture`, URL nguồn, URL bình luận nếu có, `captured_at`, chữ và số tim hiển thị. Metadata này theo dự án và timeline; API key không được đưa vào.

# Kết quả kiểm tra — 03/11/2026

## Sửa lỗi chỉ crawl 4 bình luận trên link người dùng

- Nguồn kiểm tra: https://www.threads.com/@trung_xecu_saigon/post/DfPE2liAXRS.
- Tái hiện trước sửa: đọc 77 bình luận nhưng chỉ chụp được 18; các lỗi là chỉ số thẻ thay đổi và nội dung không khớp ảnh khi Threads tái sử dụng phần tử lúc cuộn.
- Đổi sang locator theo permalink, lấy thẻ cha gần nhất, chụp theo thứ tự DOM. Lượt chạy thật sau sửa đọc 372 bình luận khác nhau, trả 120 ảnh theo số tim giảm dần; không còn bình luận lỗi chụp chưa xử lý ở cuối lượt. Không khẳng định đã đọc toàn bộ hơn 1.000 phản hồi mà nền tảng hiển thị.
- Đã xác minh đủ 120 tệp PNG được tham chiếu tồn tại, lưu dự án “Trung xe cũ · 120 bình luận đã chụp” vào ứng dụng. Không gọi TTS trả phí trong lượt kiểm tra này.
- 28 kiểm tra tự động đạt, bổ sung kiểm tra locator permalink và tiến độ/trạng thái lỗi của crawl. Bộ đếm giao diện dùng `/api/crawl-status`.
- Log lần cũ còn có profile đăng nhập đang được dùng. Sửa tạo tab đăng nhập để không để lại tab trắng; vẫn yêu cầu đóng cửa sổ đăng nhập trước khi crawl.

## Cập nhật: ảnh bình luận thật

- Đã chụp thành công 3 thẻ bình luận Threads thật, PNG 2×, giữ avatar/tên/thời gian/biểu tượng và số tim. Đã xem ảnh để loại lỗi bị lớp phủ làm tối.
- Đóng lời mời đăng nhập bằng Escape theo thao tác chuẩn; ảnh bị hộp thoại che được bỏ qua và báo lỗi, không gỡ lớp phủ bằng CSS. Một số bình luận có thể không chụp được trong cùng lần crawl; không cam kết đủ số lượng yêu cầu.
- Đã dựng thật bản MP4 720×1280 có audio bằng Google TTS, dùng 2 ảnh chụp thật và 1 cảnh meme giữa chúng. Cấu hình dự án mẫu đã thêm vào bản chạy tại C:/Su/tools/CMT_to_video mà không đổi dữ liệu/cấu hình cũ.
- 16 test tự động đạt, gồm metadata ảnh theo dự án, từ chối ghép text với phần tử khác, bỏ ảnh lỗi và từ chối phần tử bị che.
- Giao diện thực đã xác nhận có 2 ảnh gốc và metadata 1/11 tim đúng với hai ảnh; thêm version vào URL JS/CSS để trình duyệt không dùng tài nguyên cũ.
- TikTok chưa xác minh chụp bình luận thực sau thay đổi. Khi bình luận không hiển thị, trả lỗi/không có ảnh; dùng đăng nhập nguồn hoặc ảnh tự nhập.

Chi tiết hiện hành ở [comment_screenshots.md](comment_screenshots.md). Các phần kiểm chứng cũ bên dưới giữ lại theo lịch sử.

## Đã đạt

- 12 kiểm tra tự động: URL nguồn, giới hạn ID/path, nguồn TikTok đúng video và loại trùng, Threads JSON không lấy bài đề xuất, cấu trúc GraphQL reply_threads, nội dung trống, dự án lưu/mở, API key không bị trả lại, từ chối host/origin ngoài, từ chối media sai, ảnh Unicode, hủy job và retry ghi JSON khi Windows tạm khóa file.
- Kiểm tra cú pháp Python/JavaScript.
- Google TTS thực, FFmpeg thực: xuất MP4 dọc 360×640 có H.264 và AAC, ảnh bình luận tiếng Việt, meme và hiệu ứng boing.
- Smoke với giới hạn 15 giây: xuất hai phần MP4 cùng SRT và timeline, mỗi phần không vượt giới hạn với sai số mux dưới 0.15 giây.
- Dựng từ giao diện thật: dự án “Chuyện đi làm · kịch bản minh họa”, 3 bình luận và phần mở đầu, hoàn tất 17.021 giây. Hai lần dựng lại sau sửa Windows đều hoàn tất.
- Crawl Threads công khai thật: https://www.threads.com/@zuck/post/CuZsgfWLyiI, đúng bài và 5 bình luận không đăng nhập. DOM fallback được bổ sung sau lần chỉ đọc JSON có kết quả 0 bình luận.
- UI: nạp demo, lưu/mở dự án, chọn độ phân giải, gửi job, tiến độ và link MP4/SRT/timeline; không có console error ở lần kiểm tra. Đã xem bố cục desktop và bố cục hẹp. Kiểm tra layout tại chiều rộng thực 585px không có tràn ngang. Trình duyệt không áp dụng chính xác viewport yêu cầu 390px và một ảnh capture bị lỗi ghép; không dùng ảnh đó làm bằng chứng QA. Ảnh bàn giao là capture hợp lệ sau reset.

## Giới hạn đã quan sát

- TikTok: thử URL mẫu từ tài liệu chính thức https://www.tiktok.com/@scout2015/video/6718335390845095173; lấy được caption nhưng 0 bình luận trong profile không đăng nhập. Không coi crawl bình luận TikTok đã được xác minh hoạt động. Có đăng nhập riêng và nhập JSON/văn bản làm đường thay thế.
- Chưa xác minh ElevenLabs/Vbee với key thật. Không sử dụng quota trả phí. Schema Vbee cần đối chiếu dashboard của tài khoản.
- Edge TTS phiên bản đầu trên máy trả HTTP 403. Đường miễn phí mặc định đã xác minh là Google.
- 720p/1080p được hỗ trợ trong code; các bản dựng QA thực dùng 360p. Chưa benchmark thời gian dựng video nền 2 phút ở 1080p trên máy này.
- Chưa kiểm chứng mọi cấu trúc bình luận/lượt thích TikTok/Threads. Lượt thích không đọc được để 0, vì vậy cần kiểm tra trước khi xếp hạng. DOM có thể thay đổi theo ngôn ngữ hoặc thử nghiệm giao diện của nền tảng.
- Mẫu YouTube đã xem bố cục trong Chrome, chưa trích âm thanh hoặc đối chiếu timing từng frame. Media demo là tài sản minh họa tự tạo, không tái tạo chính xác gameplay/meme của mẫu.

## Đã sửa trong QA

- Windows PermissionError khi thao tác replace JSON trùng thời điểm đọc tiến độ: thêm retry ngắn và cleanup file tạm.
- Tên file audio tạm trùng khi tạo cùng nội dung đồng thời: dùng tên tạm riêng.
- Chặn cross-site quá chặt làm không mở được trang local từ tab mới: cho phép navigation GET vào trang chủ, tiếp tục chặn API từ website ngoài.
- Lỗi dùng wrapper busy với select có thể xóa options: đổi handler mở dự án.
- Tệp giả PNG: trả lỗi dữ liệu thay vì lỗi server.
- Chữ phụ quá nhỏ theo detector: nâng lên ít nhất 12px.

## Bộ bàn giao

`commentcut-source.zip` chứa mã nguồn, font/license, tests và tài liệu; không chứa .venv, key, browser profile, cache hoặc dữ liệu riêng. Folder `commentcut` trên máy hiện có môi trường cài sẵn và media/dự án demo. `commentcut-demo.mp4` là video từ lần dựng giao diện đã hoàn tất. Chạy smoke sẽ tạo thêm dự án và các tệp kiểm tra trong data.

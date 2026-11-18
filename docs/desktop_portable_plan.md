# Đóng gói CommentCut desktop portable

Mục tiêu: giải nén ZIP, mở `CommentCut.exe` để dùng trên Windows x64, không cài Python, thư viện, FFmpeg hay Chrome. Giữ cấu trúc `data/Vid_nen`, `data/img_meme`, `data/mp3_meme` cạnh EXE. Không đưa dữ liệu, API key, cookie hay media của máy đóng gói vào bản phát hành.

Kiến trúc: giữ FastAPI và editor hiện tại; Chromium đi kèm mở editor thành cửa sổ ứng dụng riêng. PyInstaller đóng gói dạng thư mục, gồm Python, thư viện, font, JavaScript, FFmpeg/ffprobe và Chromium. Crawler và đăng nhập dùng Chromium này khi chạy EXE. Khi đóng cửa sổ, dừng server. Bản mã nguồn tiếp tục dùng Chrome như hiện tại.

## Thực hiện

- [x] Kiểm thử launcher: dữ liệu cạnh EXE kể cả đường dẫn có dấu/khoảng trắng; cấu hình thư viện đi kèm; tôn trọng COMMENTCUT_DATA; lựa chọn trình duyệt và lỗi khởi động.
- [x] Sửa launcher, cấu hình crawler/đăng nhập, giữ nguyên cấu trúc media và dữ liệu đang có.
- [x] Sửa build-exe.ps1: cài phụ thuộc build tự động; tải Chromium; đóng gói FFmpeg cùng giấy phép; tạo ZIP chỉ chứa ứng dụng và các thư mục media trống.
- [x] Chạy unit/integration test; build thực; giải nén sang thư mục mới, bỏ Python/FFmpeg/Chrome khỏi PATH và kiểm tra EXE, Chromium, ảnh chụp, font, dựng MP4. Kiểm thử launcher dùng server thật và mô phỏng cửa sổ kết thúc để xác nhận server dừng.
- [x] Cập nhật README cho người đóng gói. Người dùng cuối chỉ giải nén, mở EXE và thêm media.

## Kiểm chứng

`tests/smoke_desktop.py` giải nén ZIP mới trong thư mục tạm có tiếng Việt và khoảng trắng. Tiến trình EXE chỉ có System32 trên PATH, không kế thừa cấu hình dữ liệu/FFmpeg/Playwright/API của máy build. Kiểm tra thư mục media trống trong ZIP, chạy API, tạo media bằng FFmpeg đi kèm, dùng Chromium đi kèm mở editor và chụp ảnh, dựng MP4 từ ảnh mà không gọi TTS trả phí, xác nhận luồng H.264/video và audio bằng ffprobe đi kèm.

Giới hạn: chưa thử máy Windows khác hoặc VM hoàn toàn sạch. Kiểm tra trực quan cửa sổ native bị chặn bởi lỗi công cụ Computer Use: `window id ... no longer belongs to Chrome; current owner is Chrome`. Chromium native đã được khởi chạy; bước chụp/đóng trực tiếp qua UI chưa xác minh. Bài smoke tự động chạy EXE ở chế độ không mở cửa sổ; editor được kiểm tra bằng Chromium headless đi kèm. Không gọi dịch vụ crawl/TTS thực trong smoke để tránh dùng tài khoản và quota.

Không tạo branch/commit, không thay đổi editor ngoài thông báo đăng nhập cần thiết. Giữ nguyên các thay đổi chưa commit đang có.

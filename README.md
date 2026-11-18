# CommentCut Studio — Sản xuất video bình luận hàng loạt (Desktop App)

Ứng dụng Desktop Windows chạy cục bộ để tự động biến **danh sách lớn URLs TikTok / Threads** thành hàng loạt video dọc (9:16): video nền chuyển động + ảnh chụp thật bài gốc & thẻ bình luận nhiều tim nhất + phối ngẫu nhiên đa giọng đọc **ElevenLabs** + **Video Meme / Ảnh + Tiếng Meme** lấy ngẫu nhiên từ bất kỳ thư mục nào trên máy.

## Dành cho người dùng nhận bản đóng gói (`CommentCut-Windows-x64.zip`)

1. Giải nén toàn bộ file `CommentCut-Windows-x64.zip` ra một thư mục có quyền ghi (ví dụ `D:\CommentCut` hoặc `Desktop\CommentCut` — **không** chạy trực tiếp bên trong cửa sổ xem trước của WinRAR/7-Zip và giữ nguyên thư mục `_internal` cạnh `CommentCut.exe`).
2. Mở **`CommentCut.exe`**. Ứng dụng mở trong cửa sổ Desktop App riêng (Python, FFmpeg/ffprobe và trình duyệt Chromium đã được tích hợp sẵn — **không cần cài đặt thêm bất kỳ phần mềm nào**).
3. Trong giao diện ứng dụng:
   - Vào **Giọng đọc ElevenLabs** → nhập API Key và các Voice ID rồi bấm **Lưu cấu hình ElevenLabs**.
   - Tại màn hình **Sản xuất hàng loạt** (hoặc **Thư viện & Thư mục**), bấm **`Chọn folder…`** để trỏ trực tiếp tới thư mục trên máy chứa:
     - **Video nền**: lấy ngẫu nhiên trong folder đã chọn (hoặc dùng thư mục mặc định `data/Vid_nen`).
     - **Video Meme**: lấy ngẫu nhiên các clip ngắn `.mp4`/`.mov`/`.mkv`/`.webm` kèm âm thanh gốc (có thể dùng **độc lập không cần Ảnh & Tiếng**, hoặc bật chung để trộn ngẫu nhiên).
     - **Ảnh Meme + Tiếng Meme**: khi chọn Ảnh Meme bắt buộc đi kèm Tiếng Meme (ưu tiên ghép file trùng tên như `1.png` + `1.mp3`, nếu khác tên tự động ghép ngẫu nhiên 1 ảnh với 1 tiếng).
   - Dán danh sách lớn URLs TikTok / Threads (hoặc kéo thả file `.txt`) và bấm **Bắt đầu sản xuất hàng loạt**. Video MP4 xuất ra tại `data/output/projectN` (bấm **Mở thư mục Output** trên góc phải để mở ngay trong Windows Explorer).

## Dành cho nhà phát triển / chạy từ mã nguồn

Mở `start.bat` (hoặc chạy `.venv\Scripts\python.exe launcher.py`) để mở cửa sổ Desktop App từ mã nguồn.

Đóng gói lại bản phân phối sạch cho máy khác:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-exe.ps1
```
Kết quả xuất tại:
- Bản chạy trực tiếp: `dist\CommentCut\CommentCut.exe`
- Bản nén gửi cho người khác: `dist\CommentCut-Windows-x64.zip` (tự động loại trừ toàn bộ dữ liệu cá nhân, cookie, API key của máy đóng gói)

## Kiểm thử tự động

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Lib\site-packages\playwright\driver\node.exe tests\browser_editor.cjs --screenshots
.\.venv\Scripts\python.exe tests\smoke_desktop.py dist\CommentCut-Windows-x64.zip
```

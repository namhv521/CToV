# CommentCut — Xưởng video bình luận

**Cập nhật 04/11/2026:** Chrome crawl phóng nội dung trang **125%** trước khi chụp, giữ zoom trình duyệt gốc 100% để tránh sai tọa độ khi cuộn trang. Ảnh chụp giữ trọn thẻ ở mức zoom này; ảnh cũ cần crawl lại. Crawl mặc định chụp **trọn thẻ bình luận thật** kèm avatar/tim/giao diện và ảnh đính kèm. Với video, chụp khung hình đang hiển thị hoặc poster, không tải video riêng. Chờ media tải xong; media chưa sẵn sàng được báo lỗi và thử lại, không ghi nhận ảnh chụp thiếu. Bình luận chỉ có ảnh/video vẫn được giữ và hiển thị 3 giây không đọc giọng; có thể nhập lời đọc riêng. Chữ TTS lấy riêng từ chính thẻ bình luận. Xem [chi tiết cơ chế](docs/comment_screenshots.md). Các mô tả crawl chỉ lấy chữ ở phần lịch sử bên dưới được thay bằng chế độ chụp ảnh này; nội dung nhập thủ công cũng cần gán ảnh thật; không dựng thẻ chữ thay thế.

Ứng dụng web chạy trên máy để biến bài viết và bình luận TikTok/Threads thành video dọc: nền chuyển động + ảnh bình luận + giọng Việt + meme kèm âm thanh giữa các bình luận trong cùng video; chèn ngay sau mở đầu nếu bật, không chèn sau bình luận cuối. Ảnh meme được phóng vừa khung 60% chiều rộng × 60% chiều cao, giữ tỉ lệ, tâm đặt ở 45% chiều cao màn hình.

## Chạy trên Windows

Máy hiện tại đã có môi trường `.venv` và FFmpeg. Mở `start.bat`, vào **http://127.0.0.1:8765**. Giữ tiến trình ứng dụng chạy khi dựng video.

Khi chuyển sang máy mới:

1. Cài Python 3.11 trở lên, Google Chrome và FFmpeg/ffprobe. Thêm FFmpeg vào PATH.
2. Giải nén mã nguồn, chạy `start.bat`. Lần đầu chương trình tự tạo `.venv` và cài thư viện.
3. Nếu FFmpeg chưa có trong PATH, đặt biến môi trường `FFMPEG_PATH` và `FFPROBE_PATH` thành đường dẫn tuyệt đối đến hai tệp `.exe` trước khi chạy.

Chạy thủ công:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Server chỉ nghe `127.0.0.1:8765`. Đây là công cụ cá nhân cục bộ; không đưa cổng này ra Internet. FFmpeg cài ngoài Python; không được nhúng trong ZIP.

## Quy trình sử dụng

1. **Chuẩn bị media:** đặt nền trong `data/Vid_nen`, ảnh meme trong `data/img_meme` và âm thanh cùng tên trong `data/mp3_meme` (ví dụ `1.png` + `1.mp3`, `2.png` + `2.mp3`). Meme chạy theo thứ tự số, dùng hết sẽ báo cần bổ sung hoặc tạo project mới. Thời lượng meme bằng âm thanh và được tính vào giới hạn mỗi phần. **Thư viện media:** thêm bộ video nền của bạn, ảnh meme và âm thanh meme. Có thể chọn nhiều tệp cùng loại. Mỗi tệp tối đa 500MB. Nền hỗ trợ MP4/MOV/MKV/WebM; ảnh PNG/JPG/WebP; tiếng MP3/WAV/OGG/M4A. Để thử ngay, bấm **Tạo media minh họa**.
2. **Biên tập video:** dán link TikTok hoặc Threads, chọn tối đa 10–100 bình luận rồi bấm **Lấy bình luận**. Nếu cần đăng nhập, bấm nút tương ứng, đăng nhập trong Chrome riêng, đóng cửa sổ đó rồi lấy lại dữ liệu.
3. Xem lại nội dung bài gốc. Có thể tắt đọc mở đầu.
4. Chọn, sửa, bỏ bình luận, xếp theo lượt thích hoặc dùng nút lên/xuống. Mở mục dưới từng bình luận để đặt lời đọc riêng, ảnh chụp thay thế. Meme tự chèn giữa các bình luận, chèn sau mở đầu nếu bật, không chèn sau bình luận cuối mỗi video.
5. Chọn nền, giọng, tốc độ, độ phân giải và dòng ghi nguồn. Chọn ElevenLabs để nhập 3 Voice ID theo project, dùng chung API key trong **Giọng đọc & API**. Bình luận được đọc luân phiên 1–2–3–1, liên tục qua các phần; mở đầu dùng giọng 1, bình luận không có lời đọc không chiếm lượt. Có nút nghe thử từng giọng. Để cả 3 ô trống giữ chế độ một giọng đã lưu; nhập một phần sẽ báo cần đủ 3. Hai nút **Ảnh meme** và **Âm thanh meme** bật/tắt độc lập: chỉ ảnh hiển thị 1,2 giây; chỉ âm thanh phát trên video nền; tắt cả hai bỏ đoạn meme và không cần file meme. Chỉ yêu cầu media cho phần đang bật. Dòng ghi nguồn trượt liên tục theo đường cong trong từng video, đổi hướng mượt, không nhảy vị trí giữa bình luận và meme. Chữ luôn nằm trong khung hình; để trống để tắt. Ảnh xem trước chỉ hiển thị vị trí ban đầu. **Bố cục & nhịp dựng** chứa vị trí ảnh, âm lượng, ẩn tên và thời lượng tối đa mỗi phần.
6. **Chọn kịch bản:** giữ cách chia theo thời lượng, chọn **Chia đều thành N video**, hoặc chọn **5 / 7 / 9 bình luận mỗi video** (có thể nhập số khác). Xem trước số video và các nhóm bình luận. Chỉ dùng bình luận đang chọn theo đúng thứ tự, nhóm cuối giữ phần dư. Mỗi video của kịch bản cố định lặp mở đầu nếu bật, chèn meme giữa các bình luận; nếu vượt thời lượng sẽ báo tăng giới hạn, không tự thay cách chia.
7. **Nghe thử giọng**, lưu dự án và **Dựng hàng loạt** để xuất toàn bộ video trong một lần bấm. Theo dõi tiến độ hoặc hủy. Các bản xuất nằm trong **Video đã dựng** và `data/output/projectN/`, đặt tên theo dòng đầu bài viết (hoặc tên dự án nếu bài viết trống). Video chia phần có hậu tố phần; dựng lại thêm số phiên bản để tránh ghi đè. Dữ liệu từng dự án nằm trong `data/project/projectN/`: `images`, `comments`, `audio`, `renders`, `post.json`, `project.json`. Dữ liệu cũ được giữ nguyên; dự án cũ có thư mục mới khi lưu/dựng lại.

Ảnh xem trước ưu tiên ảnh bài gốc khi bật mở đầu; nếu không thì dùng ảnh bình luận đầu tiên được chọn. Crawler chụp bài gốc trước khi cuộn đọc bình luận, lưu `post_image`, thời điểm chụp và bản ảnh trong thư mục project. Mở đầu dùng ảnh này trực tiếp. Thiếu ảnh bài gốc hoặc ảnh bình luận được chọn sẽ báo lỗi trước khi tạo giọng; không dựng thẻ chữ thay thế. Dữ liệu/project cũ cần crawl lại. Nội dung nhập tay phải gán ảnh thật cho từng bình luận; nếu có mở đầu thì cần ảnh bài gốc trong JSON project. Video nền trong preview có thể chuyển động; meme và giọng chỉ xem/nghe đầy đủ trong MP4 sau khi dựng. Thay nền minh họa bằng gameplay của bạn để gần video tham chiếu.

## Mức độ giống video mẫu

Đã quan sát video tham chiếu: https://www.youtube.com/shorts/h-t9ggZKy-A trong Chrome. Bố cục gồm gameplay dọc, ảnh hội thoại trắng phía trên tâm khung hình và dòng credit màu vàng. Công cụ tái tạo cấu trúc đó và nhịp bình luận/meme theo mô tả của người dùng.

Không có bản phân tích audio hoặc timing từng frame của mẫu. Bộ demo dùng nền kiểm tra chuyển động, ảnh chữ và hiệu ứng boing tự tổng hợp; không chứa gameplay, nhân vật hoặc audio trích từ mẫu. Vì vậy bộ demo không phải bản sao hình ảnh/âm thanh y hệt. Tải đúng background, meme và hiệu ứng mà bạn được phép sử dụng để đạt phong cách mong muốn. Ảnh meme hiện hỗ trợ ảnh tĩnh; chưa nhận GIF hoặc clip meme có chuyển động.

## Crawl hoạt động và giới hạn

Crawler dùng Playwright mở Chrome với profile riêng `data/profile`. Chỉ đọc dữ liệu công khai từ trang và phản hồi JSON mà trang nhận khi duyệt. TikTok đọc comment-list và các mục bình luận hiển thị. Threads đọc JSON có bài gốc trùng shortcode và các reply có quan hệ rõ ràng hoặc thuộc `reply_threads` của đúng bài; bổ sung các thẻ bình luận hiển thị trong cột chứa bài gốc. JSON parser loại bài đề xuất; với DOM, vẫn cần xem lại dữ liệu nếu nền tảng chèn nội dung đề xuất vào cùng cột.

Mỗi lần lấy dữ liệu có giới hạn số bình luận/thời gian. Kết quả luôn được đánh dấu có thể chưa đầy đủ. Trang có thể chặn tự động hóa, ẩn bình luận, đổi schema hoặc yêu cầu đăng nhập; khi đó kết quả có thể bằng 0. Không có cam kết lấy toàn bộ bình luận từ mọi URL. Crawler không vượt CAPTCHA, không giải mã cookie và không dùng profile Chrome cá nhân. Đã thử thật với bài công khai https://www.threads.com/@zuck/post/CuZsgfWLyiI: lấy đúng bài và 5 bình luận không đăng nhập. TikTok thử link mẫu từ tài liệu chính thức: lấy được caption nhưng 0 bình luận; chưa xác minh crawl bình luận TikTok hoạt động. Parser TikTok đã kiểm tra bằng fixture. Nút đăng nhập là bước người dùng tự làm khi cần. Bình luận crawl dài hơn 1500 ký tự hiện được giới hạn còn 1500; cần đối chiếu nguồn và chia/nhập thủ công nếu gặp nội dung dài.

API Research TikTok chính thức có điều kiện xét duyệt, không phải API bình luận tự do cho mọi tài khoản: [TikTok Research Tools](https://developers.tiktok.com/docs/en/about-research-api).

Nếu crawl thiếu, dùng **Nhập nhanh** để dán mỗi dòng:

```text
Minh | Lúc đồng nghiệp bảo hôm nay sếp nghỉ!
An | Lúc nhận lương, nhưng vui đúng năm phút.
```

Hoặc nhập JSON:

```json
{
  "comments": [
    {"author": "Minh", "text": "Tôi đọc mà cười mãi.", "likes": 128},
    {"author": "An", "text": "Câu này hay thật.", "speech": "Câu này hay thật!", "likes": 42}
  ]
}
```

Hỗ trợ nhập JSON dự án đầy đủ đã xuất từ ứng dụng. ID tài sản là tham chiếu đến thư viện trên máy; chuyển dự án sang máy khác cần chuyển cả các tài sản tương ứng. JSON xuất không chứa API key.

## Giọng đọc

### Miễn phí

**Google TTS** mặc định: tiếng Việt, không cần key, cần Internet. Đã tạo và xuất audio thực trong bản bàn giao. Đây là kết nối qua gTTS, không phải Google Cloud TTS trả phí, không có SLA. Nếu dịch vụ giới hạn thì ứng dụng báo lỗi để bạn chọn giọng khác. Không tự chuyển qua dịch vụ trả phí.

**Edge TTS**: Hoài My hoặc Nam Minh. Phiên bản Edge TTS đã thử đầu phiên trả lỗi HTTP 403; dịch vụ có thể thay đổi. Bản mã nguồn dùng edge-tts được pin trong requirements, nhưng chỉ đường Google đã được xác minh đầu cuối. Tốc độ đọc áp dụng bằng FFmpeg cho mọi provider; nghe thử dùng cùng cách xử lý tốc độ/âm lượng.

### ElevenLabs

Vào **Giọng đọc & API**, nhập API key, Voice ID và Model ID. Mặc định `eleven_v3`, hỗ trợ tiếng Việt theo [tài liệu models](https://elevenlabs.io/docs/overview/models). Có thể đổi model theo quyền và chất lượng của tài khoản. Dùng endpoint [Text to Speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).

### Vbee

Nhập Access token, App ID, Voice code và callback HTTPS do bạn quản lý. Adapter gửi `POST https://vbee.vn/api/v1/tts`, lấy `request_id`, poll `GET /api/v1/tts/{request_id}` rồi tải `audio_link`. Giới hạn poll 180 giây. Callback nhận thông tin từ Vbee; ứng dụng không cần public callback trên máy này vì lấy kết quả qua polling.

Không có key để kiểm tra hai nhà cung cấp trả phí. Tài liệu API Vbee trong dashboard không truy cập công khai được ở thời điểm thực hiện; adapter và schema cần đối chiếu tài khoản/gói API thực tế trước khi sử dụng. Không coi tích hợp Vbee đã được xác minh production. Nếu Vbee đổi schema, sửa đúng phần Vbee trong `speech.py`; phần dựng không đổi. Không có key test hoặc quota trả phí được dùng khi phát triển.

### Lưu key

Key lưu cục bộ ở `data/settings.json` khi bấm lưu. API chỉ trả trạng thái có/không có key. Ô trống giữ key cũ. Có thể dùng biến môi trường thay thế: `ELEVENLABS_KEY`, `ELEVENLABS_VOICE`, `ELEVENLABS_MODEL`, `VBEE_TOKEN`, `VBEE_APP_ID`, `VBEE_VOICE`, `VBEE_CALLBACK`. Không chia sẻ `data/settings.json` hoặc `data/profile`; đây là dữ liệu riêng. File key chưa được mã hóa bằng Windows Credential Manager.

## Cách dựng

- Nền được crop giữa thành 9:16, bỏ âm thanh gốc, loop nếu ngắn; giữ mốc nền tiếp tục giữa các cảnh.
- Mỗi bình luận thành PNG. Tự wrap chữ và thu font để vừa ảnh; không cắt chữ để vừa. Nếu quá dài, báo cần chia nội dung.
- Giọng đọc có thời lượng thật qua ffprobe, chuẩn hóa âm lượng, cộng 0.28 giây nghỉ cuối.
- Meme + hiệu ứng âm thanh xuất hiện ngay sau mở đầu và giữa các bình luận, không có sau bình luận cuối. Hai nút bật/tắt ảnh và âm thanh độc lập. Thời lượng meme theo âm thanh; chỉ ảnh là 1,2 giây.
- Mặc định 120 giây mỗi phần. Nếu toàn video dài hơn, tách tại ranh giới cảnh. Một bình luận vượt giới hạn sẽ báo lỗi; tăng giới hạn hoặc chia bình luận.
- Xuất H.264/AAC, 30 FPS, 360×640, 720×1280 hoặc 1080×1920. CPU render, một job cùng lúc, tối đa 5 job chờ/chạy.
- Job tiếp tục khi đổi trang/tab. Đóng server thì job gián đoạn, không tự resume hay tự gọi lại TTS trả phí. Mở dự án và bấm dựng lại để dùng cache giọng đã tạo.
- Hủy dừng FFmpeg đang chạy; HTTP TTS đang chờ có thể cần chờ hết timeout mới dừng. Job lỗi/hủy giữ file trung gian để kiểm tra, không quảng cáo bản xuất dở là hoàn tất.

## Thư mục và API

```text
app.py          API, bảo vệ truy cập local, hàng đợi job
core.py         model, lưu JSON atomic, ffprobe, thư viện tài sản
collector.py    crawler công khai, parser TikTok/Threads, đăng nhập riêng
speech.py       Google, Edge, ElevenLabs, Vbee và cache
render.py       ảnh PNG, audio, FFmpeg, chia phần, SRT/timeline
demo.py         bộ tài sản thử nghiệm gốc
static/         giao diện thuần và font Be Vietnam Pro (OFL)
data/assets/    tệp thư viện và metadata
data/projects/  dự án JSON
data/jobs/      từng bản dựng, log, PNG, WAV, MP4, SRT, timeline
data/cache/     audio TTS; lần dựng lại có thể dùng cache
```

OpenAPI có ở `/docs`. Các API chính: `GET/POST /api/projects`, `POST /api/crawl`, `POST /api/assets/{kind}`, `POST /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `GET/POST /api/settings`, `POST /api/voice-preview`. Đổi thư mục dữ liệu bằng `COMMENTCUT_DATA` trước khi khởi động.

Video hoàn tất có link tải trên giao diện. PNG cảnh nằm trong thư mục job. `timeline.json` ghi cấu hình và thời gian thật mỗi cảnh; SRT đồng bộ theo từng bình luận, chưa phải phụ đề karaoke theo từng từ. `ffmpeg.log` và `error.log` hỗ trợ chẩn đoán.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/smoke_render.py
```

Test đầu không gọi dịch vụ ngoài. Smoke dùng Google TTS thật, FFmpeg thật và xác nhận xuất nhiều phần có cả audio/video. Xem `docs/verification.md` để biết phần nào đã/chưa được xác minh. Font Be Vietnam Pro lấy từ [Google Fonts](https://github.com/google/fonts/tree/main/ofl/bevietnampro), kèm `static/OFL.txt`.

# Chẩn đoán hai thông báo khi dùng bản desktop

## Kết quả đối chiếu

Hai ảnh báo lỗi ở luồng đăng nhập và kiểm tra dữ liệu bình luận. Chỉ từ hai thông báo này chưa thể kết luận máy nhận thiếu thư viện, thiếu trình duyệt hoặc bị Windows chặn chụp màn hình.

Ứng dụng dùng Playwright chụp phần tử bình luận trong trình duyệt. Hai thông báo được cung cấp không phải thông báo quyền chụp màn hình của Windows.

## “Cửa sổ đăng nhập đang mở.”

Thông báo phát sinh trong `app.py`, endpoint `POST /api/login/{platform}`. Điều kiện là tiến trình đăng nhập đã được mở trước đó và `login_process.poll()` vẫn trả về `None`, nghĩa là tiến trình chưa kết thúc.

Đây là chặn mở thêm một phiên đăng nhập. Hồ sơ đăng nhập dùng thư mục `data/profile`; crawl cũng dùng hồ sơ này nên cần đóng cửa sổ đăng nhập trước khi lấy bình luận. Cửa sổ editor dùng hồ sơ riêng `data/desktop-profile`.

Nếu người nhận đã đóng cửa sổ đăng nhập mà vẫn thấy lỗi, có khả năng tiến trình con chưa thoát hoặc đang chờ một hộp thoại lỗi. Chưa có log trên máy nhận để xác nhận trường hợp cụ thể. Không được suy ra đăng nhập thành công chỉ vì tiến trình còn chạy.

Xử lý trước mắt: đăng nhập xong, đóng cửa sổ trình duyệt đăng nhập rồi bấm Lấy bình luận. Nếu thông báo còn xuất hiện dù không thấy cửa sổ đăng nhập, thoát toàn bộ CommentCut và mở lại. Không cần cài thêm thư viện để xử lý chính thông báo này.

## “Dữ liệu không hợp lệ: comments.0: Value error, Bình luận trống: cần chữ hoặc ảnh chụp.”

`comments.0` là bình luận đầu tiên. Model `Comment` trong `core.py` từ chối dữ liệu khi `text` và `image` đều trống. Trường hợp chỉ có tác giả hoặc lời đọc riêng `speech` cũng không đáp ứng điều kiện hiện tại.

Giao diện cho phép bấm Thêm bình luận để tạo một dòng trống. Việc xem trước tự động hoặc lưu dự án có thể gửi dòng đó tới server và nhận lỗi 422. Luồng Lấy bình luận trong `static/app.js` còn lưu dự án trước khi gửi `POST /api/crawl`; nếu bước lưu thất bại vì dòng trống thì crawler chưa được gọi.

Vì nhiều endpoint dùng cùng model, ảnh thông báo chưa cho biết lỗi đến từ xem trước hay lưu dự án. `data/validation_error.json` trên máy gặp lỗi ghi endpoint và các trường vi phạm, giúp phân biệt hai trường hợp.

Xử lý trước mắt: xóa dòng bình luận trống hoặc tạo Dự án mới, dán link và bấm Lấy bình luận trực tiếp. Nếu nhập thủ công, điền chữ hoặc chọn ảnh cho dòng bình luận trước khi lưu; khi dựng video vẫn cần ảnh chụp thật theo quy tắc hiện tại.

## Kiểm chứng trên mã nguồn

Đã tái hiện bằng FastAPI TestClient với thư mục dữ liệu tạm độc lập:

- Giả lập tiến trình đăng nhập còn chạy, gọi đăng nhập lần nữa: HTTP 400, đúng thông báo trong ảnh thứ nhất.
- Gửi dự án có `comments = [{"text": "", "image": ""}]`: HTTP 422, đúng thông báo trong ảnh thứ hai.
- Gửi dự án mới với `comments = []`: HTTP 200.

Chưa kiểm tra được luồng crawl thực trên máy người nhận. Nếu hết hai lỗi trên nhưng vẫn không có ảnh, cần xem thông báo trong tiến độ crawl, `data/desktop.log` và `data/validation_error.json` của đúng máy gặp lỗi. Không gửi `settings.json` hoặc thư mục profile vì chúng có thể chứa API key và phiên đăng nhập.

## Điểm cần sửa trong sản phẩm

- Luồng Lấy bình luận cần xử lý dòng nháp trống rõ ràng trước khi lưu, tránh chặn việc lấy nguồn bởi dữ liệu chưa nhập.
- Luồng đăng nhập cần báo trạng thái hoặc lỗi khởi động cụ thể; việc tiến trình tồn tại chưa đủ để biết cửa sổ đăng nhập có hoạt động.

Tài liệu này ghi nhận chẩn đoán và cách xử lý; chưa thay đổi mã ứng dụng hay tạo ZIP mới.

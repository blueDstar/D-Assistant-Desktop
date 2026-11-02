# D-bot Assistant for VS Code

Extension local cho D-bot trên Windows. Không cần API key hoặc tài khoản Marketplace để cài VSIX nội bộ.

1. Khởi động backend D-bot bằng `scripts/start.ps1` trong project D-bot.
2. Cài `artifacts/d-bot-assistant-0.2.0.vsix`, rồi reload VS Code.
3. Mở thư mục project bạn tin cậy. Bấm icon D-bot ở Activity Bar và **Chọn thư mục**.
4. Viết yêu cầu; D-bot đọc/tìm file rồi đề xuất bản sửa. Bấm **Xem diff**, sau đó **Áp dụng**. Có **Khôi phục** nếu file chưa được sửa thêm.

Command Palette:

- `D-bot: Mở trợ lý lập trình`
- `D-bot: Sửa file đang mở`
- `D-bot: Giải thích vùng chọn / file`
- `D-bot: Đọc file Markdown`
- `D-bot: Tạo project mới`
- `D-bot: Chạy task VS Code đã chọn`

File chưa lưu cần lưu trước khi tạo/áp dụng bản sửa. Lệnh giải thích có thể dùng vùng chọn làm ngữ cảnh, tối đa 6000 ký tự. Context model local có giới hạn, nên giao từng thay đổi nhỏ.

Mẫu project: Python CLI, HTML/CSS/JS, React + TypeScript, FastAPI. Việc khởi tạo không tự cài dependency hoặc chạy chương trình. Lệnh chạy task mở danh sách task trong workspace; chỉ task bạn chọn mới được VS Code thực thi.

Settings cấp ứng dụng: `dbot.endpoint` mặc định `http://127.0.0.1:8008`, chỉ cho loopback; `dbot.model` mặc định `qwen3:4b-instruct`. Model phải được tải trước bằng công cụ chuẩn bị của D-bot. Runtime không tự tải model.

Extension không hoạt động trong Restricted Mode, workspace ảo hoặc WSL/SSH. File `.env`, khóa, `.git`, `.codex`, `.agents` và dữ liệu riêng D-bot bị loại. Không cấp shell tự do cho model. Các bản gốc/diff nằm trong SQLite D-bot, không tự đưa vào Training Studio.

Backend thực hiện ghi nhiều file với hash guard và rollback khi lỗi; đây không phải filesystem transaction hay OS sandbox. Nếu process dừng giữa chừng, trạng thái là interrupted và cần kiểm tra/Khôi phục. Không khôi phục đè lên chỉnh sửa mới.

Đây là trợ lý với model local nhỏ, chưa có năng lực tương đương model Codex lớn. Luôn đọc diff và chạy kiểm tra phù hợp cho project.

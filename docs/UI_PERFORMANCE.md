# Tải giao diện theo nhu cầu

Trước thay đổi, entry JavaScript production khoảng **798,35 kB**, gzip **241,85 kB**. Markdown/math và mọi tab chức năng đều được import ngay khi mở app.

Sau thay đổi, lần build local có entry khoảng **271,32 kB**, gzip **86,02 kB**: giảm khoảng **66% JS ban đầu**. Coding, hồ sơ, ứng tuyển, Language Studio và WorkspacePanel chỉ tải khi mở tab; Markdown/KaTeX và CSS/font đi kèm tải khi cần hiển thị câu trả lời hoàn tất. Tổng assets vẫn có trên đĩa, không bị loại tính năng.

Đây là đo kích thước asset bằng Vite, không phải benchmark thời gian khởi động, tốc độ token model hoặc RAM. Mở hội thoại cũ có câu trả lời sẽ tải Markdown; lần mở đầu có thể thấy text thuần ngắn trước khi định dạng xong. Khi lỗi tải renderer, nội dung text vẫn đọc được. Lỗi tab phụ được giữ trong boundary riêng để vẫn quay về chat; trước khi reload cần sao chép nội dung chưa lưu.

CI kiểm tra manifest production, tính cả shared imports được tải sớm và chặn initial JS vượt **350 KiB**. Không cộng dynamic imports chưa cần dùng vào ngân sách ban đầu. Chạy sau build:

```powershell
node scripts/check_ui_bundle.cjs
```

TypeScript/build và 20 test frontend đã qua local, gồm giữ math delimiter ngoài fenced code và nội dung Việt/Nhật. UI loading/error states, focus và mic thật vẫn cần nghiệm thu trực quan; không suy ra từ unit tests. Chưa thay engine hoặc tốc độ model.

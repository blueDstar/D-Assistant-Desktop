# Lập trình và VS Code

1. Khởi động backend, import model 4B và chọn model coding trong Cài đặt.
2. Chỉ cấp thư mục bạn muốn làm việc. D-bot không mặc định đọc cả máy.
3. Mở tab Lập trình, đọc README/Markdown/code hoặc chọn vùng code trong VS Code.
4. Giao một việc nhỏ, xem diff, áp dụng khi phù hợp. File đã thay đổi từ lúc đề xuất sẽ bị guard từ chối.
5. Chạy kiểm tra của project và dùng Khôi phục nếu cần; không khôi phục đè lên chỉnh sửa mới.

Có mẫu Python CLI, HTML/CSS/JS, React+TypeScript và FastAPI. Tạo project chỉ tạo file, không tự cài dependencies/chạy lệnh. Model 4B có context hữu hạn, vẫn có thể viết code sai. Không có shell tự do hoặc môi trường thực thi tùy ý an toàn.

## Dựng extension 0.2.0

Sau setup runtime:

```powershell
$env:PATH = "$PWD\.runtime\node;$env:PATH"
New-Item -ItemType Directory -Force artifacts | Out-Null
.\.runtime\node\npm.cmd --prefix vscode-extension ci --ignore-scripts --no-audit --no-fund
.\.runtime\node\npm.cmd --prefix vscode-extension run package
```

Tạo thư mục `artifacts` nếu chưa có (build desktop cũng tạo thư mục này). Trong VS Code: Extensions → menu … → Install from VSIX → chọn `artifacts/d-bot-assistant-0.2.0.vsix`. Reload Window.

Mở workspace local tin cậy, icon D-bot, chọn thư mục. Command Palette có đọc Markdown, giải thích vùng chọn, sửa file, tạo project và chạy task VS Code đã chọn. Chỉ task người dùng chọn mới chạy; không có sandbox OS cho task đó. Restricted Mode/virtual workspace/WSL/SSH chưa được hỗ trợ.

Trong VS Code Settings, đặt `dbot.endpoint` là `http://127.0.0.1:8008` và **`dbot.model` là `dbot-qwen35:4b`**. Mặc định extension còn dùng tag fallback cũ `qwen3:4b-instruct`; thay rõ nếu chưa tải tag đó. Chỉ endpoint loopback được chấp nhận.

File chưa lưu cần lưu trước khi sửa. `.env`, khóa, thư mục metadata và dữ liệu riêng của D-bot bị loại khỏi quyền đọc. Bản gốc/diff ở SQLite local; không tự thành ví dụ học.

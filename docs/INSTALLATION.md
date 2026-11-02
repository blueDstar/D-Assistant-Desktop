# Cài mới trên Windows x64

Chạy từ thư mục gốc repository. Không cần tài khoản cloud cho inference local. Cần Internet để lấy runtime/dependencies/model; sau đó runtime chỉ dùng tài sản đã có. Chưa có bộ cài all-in-one và chưa nghiệm thu fresh-install trên máy thứ hai.

## 1. Chuẩn bị môi trường

Cài Git và Python >=3.9 có lệnh `python` hoạt động. Bootstrap tạo Python 3.12 riêng qua uv, Node LTS, Ollama portable; không thay Python/Node mặc định của máy. Runtime bootstrap lấy release hiện hành, nên không bảo đảm giống hệt phiên bản của máy phát triển.

```powershell
git clone https://github.com/blueDstar/D-Assistant-Desktop.git
cd D-Assistant-Desktop
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

`.env.example` được copy thành `.env` nếu chưa có. Giữ `.env` local. Dependencies được khóa trong `backend/uv.lock` và các `package-lock.json`. `-SkipVoice` bỏ nhóm voice nếu chỉ cần text; cần chạy setup đầy đủ trước khi dùng voice.

## 2. Tải và import LLM

Các script Qwen3.5 tải revision cụ thể, kiểm tra size/hash, ghi manifest local. Script 4B cũng tải Whisper Small cho học ngôn ngữ. Weights 4B khoảng 2,74 GB và 2B khoảng 1,28 GB; dung lượng tải không phải tổng RAM lúc chạy. Dành thêm nhiều GB cho runtime, dependencies, voice và cache; Ollama có thể tạo bản lưu weights thứ hai khi import.

```powershell
.\.venv\Scripts\python.exe -X utf8 .\scripts\prepare_models_v6.py
.\.venv\Scripts\python.exe -X utf8 .\scripts\prepare_fast_model_v62.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
.\.runtime\ollama\ollama.exe create dbot-qwen35:4b -f .\models\qwen35-4b.Modelfile
.\.runtime\ollama\ollama.exe create dbot-qwen35:2b -f .\models\qwen35-2b.Modelfile
```

Có thể bỏ hai lệnh 2B nếu chỉ dùng 4B. Các Modelfile mẫu đặt CPU, 4 thread, context 4096/3072 và temperature 0.3. Chỉnh theo phần cứng sau khi đo, không giả định GPU cũ hỗ trợ tốt. Không tự xóa model cũ hoặc cache trên máy khác.

**Nếu đã có Ollama:** launcher tái sử dụng server ở 127.0.0.1:11434 và không sở hữu/dừng server đó. Kiểm tra chế độ cloud của server bạn tự quản lý; import sẽ ghi vào kho của server đang chạy. Mặc định khi launcher tự tạo server, kho nằm trong `data/models/ollama` và cloud bị tắt. Không chạy hai server cùng port.

## 3. Voice tùy chọn

```powershell
.\.venv\Scripts\python.exe -X utf8 .\scripts\prepare_models.py --voice
.\.venv\Scripts\python.exe -X utf8 .\scripts\prepare_language_tts.py
```

Lệnh đầu tải Whisper Base và Piper Việt; lệnh sau tải Kokoro FP32 và voices Anh–Nhật. Whisper Small đã có từ bước 2. Engine không tự tải weights khi trò chuyện. Lần chuẩn bị base/Piper chọn revision upstream hiện tại và ghi manifest; không phải toàn bộ assets đều pin từ trước như Qwen3.5. Xem điều khoản voice trong [third-party notices](THIRD_PARTY_NOTICES.md).

## 4. Dựng và mở desktop

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-desktop.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\desktop.ps1
# Tùy chọn tạo shortcut trên Desktop:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-desktop-shortcut.ps1
```

Đặt nguyên cây project tại vị trí sử dụng. EXE trong `artifacts/D-bot-Desktop` tìm backend/scripts ở các thư mục cha; không copy mỗi EXE sang chỗ khác. Shortcut là thao tác riêng, không đăng ký tự chạy cùng Windows.

Vào Cài đặt: đặt tên/cách xưng hô, model chính `dbot-qwen35:4b`, model nhanh `dbot-qwen35:2b` nếu đã import, model coding `dbot-qwen35:4b`. Đặt ngôn ngữ STT/tốc độ giọng theo nhu cầu. Học từ hội thoại mặc định tắt ở bản cài mới. Chọn thư mục được phép đọc, không cấp cả ổ đĩa.

Đóng cửa sổ chính giữ robot. Ctrl+Alt+D hiện lại cửa sổ khi desktop đang chạy; menu khay để ẩn robot/thoát. Backend có thể vẫn chạy; dừng riêng bằng:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

## Khi có lỗi

| Hiện tượng | Kiểm tra |
|---|---|
| Không có model / tag not found | Xem `ollama list`, import đúng tag và kiểm tra Cài đặt; tải GGUF chưa đồng nghĩa đã import |
| Không mở desktop | Chạy setup-desktop, giữ EXE trong cây project, kiểm tra `.env` và frontend/dist |
| Câu trả lời lâu | Xem model thực tế, RAM trống và context; dùng 2B cho chat thường, chia nhỏ tác vụ 4B |
| Nói xong không gửi | Chọn đúng mic/quyền mic, giảm tiếng nền, dùng “Xong, gửi”; lỗi STT vẫn có thể xảy ra |
| Không có tiếng | Kiểm tra voice assets, thiết bị phát, âm lượng và trạng thái prepare; không có cloud fallback |
| Không đọc/sửa được file | Cấp đúng thư mục, lưu file, tránh vùng dữ liệu riêng/secrets; không tắt guard để lách quyền |
| Backend không lên | Xem `data/logs/backend.err.log`, `ollama.err.log`; chạy diagnose.ps1 |

`scripts/diagnose.ps1` có thể ghi thông tin máy local; không đăng log/health/settings đầy đủ lên issue khi chưa loại thông tin cá nhân. Nếu dùng port khác 8008, cập nhật `.env`, dev proxy và endpoint extension tương ứng.

# Phát triển

Repository có CI Windows cho backend, frontend build/tests và desktop logic. Workflow không dùng secrets, chỉ đọc repository; không tải weights LLM. Badge README trỏ tới kết quả chạy thực tế. Xem [CONTRIBUTING.md](../CONTRIBUTING.md) để gửi PR.

Chạy setup trước. Dùng runtime portable thay vì thay PATH toàn máy:

```powershell
$env:PATH = "$PWD\.runtime\node;$env:PATH"
.\.runtime\node\npm.cmd --prefix frontend run typecheck
.\.runtime\node\npm.cmd --prefix frontend run build
.\.runtime\node\node.exe --experimental-strip-types --test frontend/tests/*.test.cjs frontend/tests/*.test.ts
.\.runtime\node\npm.cmd --prefix desktop test
.\.venv\Scripts\python.exe -X utf8 .\scripts\prepare_test_tokenizer.py
Push-Location backend
..\.venv\Scripts\python.exe -X utf8 -m pytest -q
Pop-Location
```

Backend test dùng database tạm và phần lớn mock LLM, không đòi weights LLM nhưng **cần tokenizer local** để kiểm tra ngân sách context chính xác. Lệnh prepare_test_tokenizer tải riêng tokenizer Qwen3.5 và Qwen3 (tag cũ còn trong fixture), pin revision, cần Internet lần đầu. Khi chưa có tokenizer, runtime ước lượng bảo thủ theo byte UTF-8 và nhiều test context sẽ từ chối câu hỏi; không xem kết quả đó là bộ test đầy đủ đã qua. Một số test optional voice phụ thuộc nhóm voice của setup. Không chạy trực tiếp trên database người dùng bằng test/ad-hoc script.

Frontend dev: `npm --prefix frontend run dev` sau khi khởi động backend; Vite chỉ bind loopback, proxy mặc định port 8008. Khi đổi `.env` port backend, chỉnh Vite proxy và extension endpoint tương ứng.

Sau khi sửa detector hoặc robot, chạy `node scripts/build_voice_detector.cjs` / `node scripts/build_pet_moods.cjs`. Dựng desktop dùng `scripts/setup-desktop.ps1`; đóng native app trước khi ghi đè gói đang chạy. Build desktop không kèm `.env`, data hoặc weights, nhưng bản đóng gói vẫn cần các tài sản đó ở cây project bên ngoài.

Extension: xem [CODING_GUIDE.md](CODING_GUIDE.md); có `npm --prefix vscode-extension test`. `scripts/probe_tools.py --model TAG` thử calculate với model thật và lưu registry theo digest; đây không phải trainer hoặc bài kiểm tra năng lực tổng quát.

Trước khi push: kiểm tra diff, ignore, thông tin riêng và file lớn; không thêm runtime/model/database/log. Tài liệu ảnh SVG trong docs/images là minh họa có dữ liệu demo; không mô tả thành screenshot thật. Khi cần screenshot thật, dùng phiên demo và che thông tin riêng trước khi chia sẻ.

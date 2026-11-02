# Kiểm tra bản nguồn công khai — 02/11/2026

Kiểm tra trên cây mã nguồn xuất bản riêng, dùng Python/dependencies từ môi trường phát triển và npm dependencies cài bằng lockfile. Không thay đổi dữ liệu đang dùng hoặc khởi động lại trợ lý của chủ máy.

| Kiểm tra | Kết quả |
|---|---|
| Backend regression | **94 passed, 1 skipped** sau khi chuẩn bị tokenizer Qwen3/Qwen3.5 |
| Frontend | **18 passed**; TypeScript và production build qua |
| Desktop logic | **18 passed** |
| README và ảnh | 3 hình SVG render thành PNG, đã xem lại; nội dung demo được ghi rõ |
| Tài liệu | Kiểm tra liên kết tương đối, Modelfile và đường dẫn script |
| Rà soát nguồn | Không thấy khóa theo các mẫu kiểm tra hoặc email/đường dẫn tài khoản chủ máy; ignore chặn dữ liệu/runtime/weights; diff không có lỗi whitespace |
| Phạm vi xuất bản | Chỉ source/tests/lockfiles/tài liệu; không có data, runtime, weights, CV/email/backup/log riêng |

Lần test backend đầu trên cây sạch: 19 failed, 75 passed, 1 skipped vì chưa có tokenizer. Đã xác định nguyên nhân ước lượng token dự phòng theo byte UTF-8, bổ sung script chuẩn bị tokenizer pin revision, rồi chạy lại toàn bộ thành công. Không sửa test để bỏ qua ngân sách context.

Build Vite có cảnh báo chunk JS khoảng 798 kB vượt ngưỡng 500 kB; build vẫn thành công. Code splitting còn trong hướng tối ưu, chưa giải quyết trong lần xuất bản tài liệu.

Chưa thử cài lại toàn bộ runtime/voice/model trên máy sạch, chưa kiểm tra mic/nghe thật hoặc layout bằng native UI. Test frontend/desktop dùng fake/mocks cho phần tương tác. Không coi việc xuất bản repository là bản phát hành installer đã nghiệm thu.

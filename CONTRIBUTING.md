# Đóng góp cho D-bot

Chọn một vấn đề có thể tái hiện hoặc một tính năng có tiêu chí nghiệm thu cụ thể. Với thay đổi lớn, trao đổi phạm vi qua issue trước. Mỗi PR nên giải quyết một vấn đề hoàn chỉnh; không chia nhỏ thay đổi chỉ để tăng số PR.

1. Tạo nhánh từ main và dùng dữ liệu demo.
2. Giữ quyền loopback, allowlist file và duyệt diff; không thêm quyền ngầm định.
3. Chạy kiểm tra phù hợp trong [DEVELOPMENT](docs/DEVELOPMENT.md). Context tests cần tokenizer; không cần tải weights LLM.
4. Mở PR, giải thích hành vi trước/sau, bằng chứng và phần chưa kiểm tra.
5. Chờ CI và xử lý lỗi trước khi merge. CI không thay nghiệm thu mic, UI hoặc inference thật.

CI chạy trên Windows với lockfiles, chỉ quyền đọc repository, không dùng secrets, không cài Ollama hoặc tải LLM weights. Tokenizer tải từ revision đã pin. Tests backend có dependencies voice để kiểm tra decode/tempo giả lập; việc này không xác nhận chất lượng giọng thực tế.

Chỉ ghi đồng tác giả khi có đóng góp thật và người đó đồng ý gắn danh tính. Đóng góp do AI hỗ trợ cần mô tả trung thực; không gán người không tham gia vào commit. Không đăng câu trả lời/issue lặp lại để lấy huy hiệu.

Project chưa có giấy phép phân phối chung. Hãy đọc LICENSE.txt và third-party notices trước khi đề xuất phân phối, sao chép branding hoặc model/voice.

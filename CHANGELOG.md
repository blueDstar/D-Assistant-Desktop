# Changelog

## Desktop 0.6.2

- Hội thoại ưu tiên ở sidebar, nhóm chức năng thu gọn, quản lý dự án và đổi tên/chuyển chat.
- Detector giọng nói dùng chung, tự kết thúc lượt sau khoảng 750 ms im lặng và nút kết thúc thủ công.
- Prompt gọn cho chat ngắn; 2B chỉ ưu tiên chat Việt thông thường, 4B cho kỹ thuật/Anh–Nhật/coding.
- Phục hồi kích thước cửa sổ robot ngoài dự kiến, bounds và đảo chiều ở rìa màn hình.
- Worker tách thời gian khởi động khỏi giới hạn chạy công cụ, hủy khi disconnect.

## Desktop 0.6 / 0.6.1

- Qwen3.5-4B local, Language Studio Anh–Nhật, Whisper Small và Kokoro.
- Tiếp tục trả lời dài giữ câu hỏi gốc; hàng đợi giọng đọc và hủy phát cũ.
- Training Studio quản lý mẫu chờ duyệt; không fine-tune trọng số.

## Desktop 0.3 / 0.4 và coding 0.2

- Electron, tray, floating robot và lệnh ứng dụng có xác nhận.
- Đọc/tìm file, diffs có hash guard và khôi phục, project templates.
- Extension VS Code 0.2.0 cho workspace local đáng tin cậy.

## Bản nguồn công khai

- README, 3 hình minh họa SVG/PNG, hướng dẫn cài/dùng/phát triển và roadmap.
- Modelfile mẫu và chuẩn bị tokenizer test riêng, không cần tải weights LLM để chạy regression.
- Mặc định hồ sơ/email chung; không phân phối dữ liệu người dùng, runtime, model hoặc log riêng.
- Bản công khai chưa có installer độc lập hoặc giấy phép phân phối chung.

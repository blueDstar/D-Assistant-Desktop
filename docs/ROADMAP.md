# Hướng nâng cấp

Các mục dưới đây là kế hoạch, chưa phải tính năng đã hoàn tất và chưa có ngày cam kết.

| Ưu tiên | Hạng mục | Điều kiện nghiệm thu |
|---|---|---|
| 1 | Voice thực tế | Mic thật ở phòng yên/ồn, câu ngắn/dài, Việt/Anh/Nhật; không mất transcript, không tự hiểu sai xác nhận |
| 1 | Desktop và khả năng truy cập | Chuột/wheel, IME, nhiều màn hình/DPI, mép màn hình, sleep/resume và keyboard navigation |
| 1 | Tốc độ | Benchmark cùng câu hỏi/context, warm/cold nhiều lượt; báo P50/P95, RAM peak, thời gian STT/LLM/TTS riêng |
| 1 | Cài đặt tái lập | Pin runtime, cài mới ở máy sạch, build/upgrade/rollback; bộ cài ký và giữ dữ liệu khi nâng cấp |
| 2 | Anh–Nhật | Mở rộng bài tập có nguồn/quyền sử dụng, đánh giá rubric bởi người có chuyên môn, kiểm tra chống đáp án sai |
| 2 | Coding | Benchmark sửa nhiều file, syntax/tests, phục hồi khi crash; chỉ thêm thực thi khi có sandbox OS phù hợp |
| 2 | Tài liệu | OCR và vector embeddings local, quản lý version/xóa chỉ mục, benchmark citation đúng nguồn |
| 2 | Gmail/Calendar | OAuth tối thiểu, consent theo hành động, chống gửi trùng, audit log, watcher có bật/tắt và xác minh lịch |
| 3 | Fine-tuning | Dataset được duyệt, holdout độc lập, phần cứng phù hợp, trainer thật, so sánh chất lượng/rollback adapter |
| 3 | Đa phương thức | Chọn vision/audio model theo RAM/VRAM thực, benchmark và giới hạn quyền camera; chưa cam kết any-to-any |

Chưa tự bỏ giới hạn context/token hoặc thay model lớn hơn chỉ để gọi là “không giới hạn”. Chỉ chuyển model mặc định sau kiểm tra chất lượng, tài nguyên và thời gian đáp ứng. Cập nhật docs và trạng thái kiểm thử cùng mỗi bản phát hành.

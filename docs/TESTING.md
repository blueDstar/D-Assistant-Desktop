# Phạm vi kiểm thử

## Mốc local 0.6.2 trước xuất bản

| Nhóm | Kết quả ghi nhận | Giới hạn |
|---|---|---|
| Backend | 93 passed, 1 skipped; 23 test liên quan chạy lại sau routing cuối | Nhiều API test dùng LLM mock; không cộng phần chạy lại |
| Frontend | 18 passed; typecheck và production build qua | Mock audio/microphone; không phải thao tác UI thật |
| Desktop | 18 passed | Fake BrowserWindow và chuỗi thoại; không thay mic/chuột thật |
| Native package | 29 file hash khớp manifest; main/pet/chat đã load | Không xác nhận bố cục, focus hoặc âm thanh bằng mắt/tai |
| Model local | Có gọi Ollama thật, streaming, context và thử công cụ | Bộ mẫu nhỏ; đã quan sát lỗi nội dung |

Không kèm log/QA gốc vì có dữ liệu riêng. Bảng là ghi nhận nghiệm thu trên máy phát triển, không phải kết quả CI của bản clone mới. Kết quả kiểm tra bản nguồn xuất bản nằm ở [PUBLICATION_CHECKS.md](PUBLICATION_CHECKS.md).

## Tốc độ và chất lượng

CPU i5-1035G1, RAM khoảng 8 GB. Mẫu chat Việt ngắn dùng 2B: 305 input tokens, 39 output tokens, chữ đầu khoảng 9,3 giây, tổng khoảng 13,6 giây. Chưa có phân phối P50/P95. Câu trả lời mẫu vẫn có diễn đạt chưa hợp lý; tốc độ không xác nhận chất lượng.

4B từng mất vài phút khi máy thiếu RAM. Giảm prompt chưa cho thấy cải thiện ổn định ở mọi phép thử. Không dùng số chat 2B để hứa tốc độ tương tự cho research/coding/Anh–Nhật trên 4B.

2B từng không tuân thủ yêu cầu chỉ trả tên, dịch thay vì sửa câu tiếng Anh, và giải thích sai vai trò D trong PID. Vì vậy auto routing tránh dùng 2B cho các nhóm khó này; vẫn phải kiểm tra heuristic và câu trả lời 4B.

## Chưa kiểm tra đầy đủ

- Mic vật lý, phát/nghe giọng, endpointing với người dùng thật, giọng nhỏ/tiếng nền và ngắt theo giọng.
- Chuột/wheel khi robot nổi, IME/focus, nhiều màn hình/DPI và layout trực quan.
- Cắt Internet thực tế sau chuẩn bị assets, cài mới trên máy sạch và phần cứng khác.
- Bảo đảm chất lượng chứng chỉ, lập trình tổng quát, bảo mật toàn bộ dependency hoặc fine-tune trọng số.

## Chạy lại

Xem [DEVELOPMENT.md](DEVELOPMENT.md) cho lệnh. Test giả lập phải được báo riêng với inference thật. Không sử dụng chat/CV/email riêng làm fixture công khai. Test tool/model thật chỉ chạy trên model đã chuẩn bị và có thể tốn nhiều phút.

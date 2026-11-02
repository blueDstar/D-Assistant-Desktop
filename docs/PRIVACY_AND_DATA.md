# Dữ liệu và quyền truy cập

Kho GitHub chỉ chứa source, tests, lockfiles, script chuẩn bị và tài liệu công khai. Không chứa `.env`, SQLite, CV, email, lịch hẹn, hồ sơ chủ máy, chat, backups, model weights, runtime, log hoặc báo cáo QA riêng. Các script nhập portfolio/lịch sử ứng tuyển và thử nghiệm gắn dữ liệu máy gốc được giữ local, không phân phối.

**Trên máy người dùng:** `data/` chứa database, tài liệu, models, exports/backups và trạng thái desktop. Bật lịch sử sẽ lưu chat. Chế độ riêng tư không lưu lượt chat nhưng hồ sơ cá nhân vẫn có thể được đưa vào ngữ cảnh nếu bạn chưa tắt hồ sơ. Không xem private chat là tắt mọi ngữ cảnh cá nhân.

Audio phục vụ STT ở vùng tạm; bản hiện tại không cung cấp chế độ lưu raw audio làm lịch sử. TTS/STT dùng engine local khi đã chuẩn bị. Đây chưa phải kiểm toán forensic việc xóa dữ liệu trên đĩa.

Hồ sơ có thể xem/sửa/tắt/xóa; memory và training examples có scope/quyền duyệt. Xóa một bản ghi không xóa tự động các bản export/backup bên ngoài hoặc email/Calendar gốc. Giữ backup cẩn thận. Backup SQLite nhất quán và restore kiểm tra ở thư mục mới; không ghi đè DB đang dùng.

Backend chỉ bind loopback, kiểm tra Host/Origin và token phiên cho mutation. File access yêu cầu allowlist và có path guards. Các lớp này không thay Windows account security: phần mềm độc hại chạy cùng tài khoản vẫn là rủi ro. Không đưa backend ra Internet và không đổi CORS/host guard để làm server công cộng.

Tích hợp ngoài như Gmail/Calendar cần cấp quyền riêng và phải giữ biên nhận thật. Không gửi/draft/lên lịch ứng tuyển trước khi người dùng duyệt đúng JD. Không tự nhận đã đặt lịch phỏng vấn từ nội dung suy đoán.

Trước khi chia sẻ issue/log: loại tên máy, đường dẫn tài khoản, profile, email, CV, token, message IDs và nội dung chat. `.gitignore` chỉ là lớp ngăn commit ngoài ý muốn; vẫn kiểm tra diff trước mỗi lần push.

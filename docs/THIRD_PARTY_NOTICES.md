# Nguồn, phiên bản và giấy phép

Không gán giấy phép chung cho tài sản người dùng hoặc model chỉ từ license repository. Model/voice/runtime tải cục bộ bị gitignore; không đưa vào mã nguồn để phân phối. Giữ các notice đi kèm dependency và kiểm tra nghĩa vụ tương ứng trước khi đóng gói/phân phối.

## Runtime và model

Đợt 0.6 thêm Qwen3.5-4B Q4_K_M ([base Qwen](https://huggingface.co/Qwen/Qwen3.5-4B), [GGUF Unsloth](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF), Apache-2.0), [Whisper Small CTranslate2](https://huggingface.co/Systran/faster-whisper-small) (MIT theo model card), [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0 weights) và [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (MIT). Tệp model có revision/hash ở các manifest `data/models`; dependencies G2P Nhật, từ điển và ONNX được khóa trong `backend/uv.lock`, giữ notices đi kèm gói đã cài. Các câu trắc nghiệm trong `language_questions.json` tự biên soạn, không sao chép đề thi chính thức. Các dòng Qwen3 1.7B/Coder bên dưới ghi lịch sử, hai tag này đã được dọn khỏi runtime 0.6.

| Thành phần | Nguồn và ghi chú |
|---|---|
| Ollama 0.40.11 | [Ollama](https://github.com/ollama/ollama), MIT; archive Windows x64 tải từ release chính thức, SHA256 kiểm tra từ metadata release. Bản đang dùng chỉ trích xuất phần CPU |
| Qwen3 4B Instruct 2507 / Q4_K_M | [Model card Qwen](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), Apache-2.0; [tag Ollama](https://ollama.com/library/qwen3:4b-instruct). Digest tùy bản tải, kiểm tra server local |
| Qwen3 1.7B / Q4_K_M | [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B), Apache-2.0; model nhẹ dự phòng, có lỗi số học trong kiểm tra |
| Qwen2.5 Coder 1.5B Instruct | [Tag Ollama](https://ollama.com/library/qwen2.5-coder:1.5b-instruct), Apache-2.0 theo license thực từ `/api/show`; manifest/digest và tokenizer revision/hash ở `data/models/coding-model-manifest.json`. Chỉ là ứng viên model, đã quan sát lỗi chọn công cụ/kết luận sai trong nghiệm thu |
| Python 3.12.15 | Managed CPython từ uv/python-build-standalone, giữ license trong runtime; [Python license](https://docs.python.org/3/license.html) |
| Node 24.22.1 | [Node.js](https://nodejs.org/), MIT và notices thành phần kèm theo; archive đối chiếu SHA256 từ SHASUMS256 chính thức |
| uv 0.13.5 | [Astral uv](https://github.com/astral-sh/uv), MIT hoặc Apache-2.0; archive release chính thức |
| Whisper base | [Systran/faster-whisper-base](https://huggingface.co/Systran/faster-whisper-base); trọng số chuyển đổi Whisper, đối chiếu model card/MIT nguồn Whisper; revision/hash tài sản trong `data/models/voice-manifest.json` |
| Piper engine 1.8.0 | [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl), **GPL-3.0-or-later** theo metadata gói đã cài; không suy thành MIT từ repo voice |
| Voice vi_VN-vais1000-medium | [MODEL_CARD riêng](https://huggingface.co/rhasspy/piper-voices/blob/main/vi/vi_VN/vais1000/medium/MODEL_CARD), vi_VN, 22.050 Hz, 1 speaker; card nêu dataset VAIS1000 CC BY 4.0, fine-tune từ lessac medium. Card không diễn đạt license trọng số riêng rõ như license dataset; cần xác minh thêm trước khi phân phối voice. Không tự gán MIT của repository cho voice |

## Dependency chính đã cài

Phiên bản đầy đủ và hashes dependency nằm trong `backend/uv.lock`, `frontend/package-lock.json`.

Extension có `vscode-extension/package-lock.json`: TypeScript 5.9.3, VS Code API types 1.95.0 và vsce 4.0.0 phục vụ build/test/package. VSIX không đóng gói `node_modules` hay công cụ đóng gói/Azure auth. Icon D-bot extension là SVG riêng tạo trong workspace. Extension dùng nội bộ, chưa xuất bản Marketplace.

| Dependency | Phiên bản đã thử | License theo metadata/nguồn dự án |
|---|---|---|
| FastAPI | 0.162.0 | MIT |
| Uvicorn | 0.54.0 | BSD-3-Clause |
| Pydantic | 2.14.1 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| pypdf | 6.21.2 | BSD-3-Clause |
| python-docx | 1.2.0 | MIT |
| faster-whisper | 1.2.1 | MIT |
| CTranslate2 | 4.8.4 | MIT |
| PyAV | 16.1.0 | BSD-3-Clause; wheel mang thư viện FFmpeg và notices tương ứng |
| ONNX Runtime | 1.31.0 | MIT |
| Hugging Face tokenizers | 0.23.3 | Apache-2.0 theo dự án |
| React / React DOM | xem package-lock | MIT |
| Vite 7.3.7 / TypeScript | xem package-lock | MIT / Apache-2.0 |
| react-markdown / remark-gfm / remark-math / rehype-katex | xem package-lock | MIT |
| KaTeX + font kèm theo | xem package-lock | MIT và notice font kèm gói |

Không tuyên bố bảng trên thay thế kiểm toán license toàn bộ dependency bắc cầu khi phân phối sản phẩm. SQLite là thành phần chuẩn Python, public domain theo dự án SQLite.

## Nhận diện blueDStar

Tokens và 14 icon được sao chép từ style kit người dùng trong workspace; chỉ gồm tokens/icon giao diện, không kèm toàn bộ kit. Không lấy ảnh cá nhân, mesh OpenArm/Unitree, font thương mại hoặc placeholder hình dự án để phân phối. Kit không được nhập vào RAG hoặc dataset.

## Tài liệu kỹ thuật đã đối chiếu

- [Ollama chat API](https://docs.ollama.com/api/chat), [tool calling](https://docs.ollama.com/capabilities/tool-calling), [FAQ](https://docs.ollama.com/faq), [GPU](https://docs.ollama.com/gpu).
- [FastAPI](https://fastapi.tiangolo.com/python-types/), [Vite](https://vite.dev/guide/), [Node downloads](https://nodejs.org/en/download).
- [faster-whisper chính thức](https://github.com/SYSTRAN/faster-whisper), [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md), [PyAV 16.1.0](https://pypi.org/project/av/16.1.0/).

Đối chiếu tài liệu không thay kiểm tra thực tế: lỗi decoder PyAV 19 đã được phát hiện trên máy và khóa về 16.1.0, ghi lại trong VOICE_SETUP/TEST_REPORT.

## Bổ sung model chat nhanh 0.6.2

[Unsloth Qwen3.5-2B-GGUF](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF), Q4_K_M, Apache-2.0 theo model card; revision trong scripts/prepare_fast_model_v62.py; hash và manifest ghi ở data/models sau khi tải. Chỉ tải weights và cấu hình, không chạy mã từ repository và không gửi hội thoại ra ngoài.

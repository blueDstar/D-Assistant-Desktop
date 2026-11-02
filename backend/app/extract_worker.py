"""Bounded extraction worker; never executes source code or document macros."""
import json
from pathlib import Path
import sys
import zipfile

TEXT_EXTENSIONS = {".txt", ".md", ".py", ".c", ".cpp", ".h", ".hpp", ".ino", ".csv", ".json", ".yaml", ".yml", ".log", ".rs", ".ts", ".js"}


def extract(path):
    suffix = path.suffix.lower()
    if path.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("Tài liệu vượt giới hạn 12 MiB")
    if suffix in TEXT_EXTENSIONS:
        raw = path.read_bytes()
        if b"\x00" in raw:
            raise ValueError("File nhị phân không được nhập như text")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Không đọc được UTF-8. Hãy lưu lại tài liệu với encoding UTF-8.")
        sections = [(text, "dòng", 1)]
        method = "utf8-lines"
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("PDF có mật khẩu. Hãy xuất bản không mã hóa trước khi nhập.")
        if len(reader.pages) > 200:
            raise ValueError("Tối đa 200 trang PDF mỗi file")
        sections = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text()
            if len(text) > 100000:
                raise ValueError(f'Trang PDF {index + 1} vượt 100.000 ký tự; chia tài liệu trước khi nhập')
            sections.append((text, f'trang PDF {index + 1}, dòng', 1))
        method = "pypdf-text"
    elif suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 32 * 1024 * 1024 or len(archive.infolist()) > 1000:
                raise ValueError("DOCX giải nén vượt giới hạn")
        from docx import Document
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs]
        paragraphs.extend(" | ".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows)
        sections = [("\n".join(paragraphs), "mục trích xuất", 1)]
        method = "python-docx-paragraphs"
    else:
        raise ValueError("Định dạng không được hỗ trợ")
    if not any(s[0].strip() for s in sections):
        raise ValueError("Không có text. PDF scan cần OCR; V1 chưa có OCR.")
    if sum(len(s[0]) for s in sections) > 400000:
        raise ValueError("Text vượt 400.000 ký tự. Chia tài liệu thành phần nhỏ.")
    chunks = []
    for text, location, offset in sections:
        lines = text.splitlines()
        start = 0
        while start < len(lines):
            end = start
            length = 0
            while end < len(lines) and (length < 700 or end == start) and end - start < 24:
                length += len(lines[end]) + 1
                end += 1
            content = "\n".join(lines[start:end]).strip()
            # Long single lines are split with offsets retained, never silently discarded.
            for index in range(0, len(content), 1000):
                fragment = content[index:index + 1000]
                if fragment:
                    chunks.append({"content": fragment, "location": f"{location} {start + offset}–{end + offset - 1}" + (f", ký tự {index + 1}–{index + len(fragment)}" if len(content) > 1000 else "")})
            start = max(start + 1, end - 2) if end < len(lines) else end
    return {"method": method, "chunks": chunks}


if __name__ == "__main__":
    try:
        print(json.dumps(extract(Path(sys.argv[1])), ensure_ascii=False))
    except Exception as error:
        sys.stderr.write(f"{type(error).__name__}: {error}")
        sys.exit(1)

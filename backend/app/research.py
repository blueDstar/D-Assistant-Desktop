"""Project-scoped retrieval, versioned memory, real sources and notes."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import Field

from . import db
from .config import DATA, MAX_UPLOAD, ROOT
from .prompts import build_context, token_cost
from .schemas import StrictModel

router = APIRouter(prefix="/api", tags=["research"])
JOB_CANCEL: dict[str, asyncio.Event] = {}
STOP_WORDS = set('tôi mình bạn hãy giúp cho của một những các là có không với trong này đó và hoặc về được như thế nào gì bao nhiêu theo để từ đang hỏi tài liệu the a an what how is are of in to me please'.split())


def require_project(id):
    if not db.one("SELECT id FROM projects WHERE id=?", (id,)):
        raise HTTPException(404, "Không tìm thấy dự án")


def search(query, project_id, source_ids=None, limit=5):
    tokens = [word for word in re.findall(r"[^\W_]+", query.lower(), re.UNICODE) if len(word) >= 2 and word not in STOP_WORDS][:20]
    if not tokens:
        return []
    scope = "c.project_id=? AND s.status='ready'"
    args = [project_id]
    if source_ids:
        scope += " AND s.id IN (" + ",".join("?" for _ in source_ids) + ")"
        args.extend(source_ids)
    columns = "c.*,s.filename,s.version,s.hash"
    try:
        result = db.rows(f"SELECT {columns},bm25(chunks_fts) AS rank FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid JOIN sources s ON s.id=c.source_id WHERE {scope} AND chunks_fts MATCH ? ORDER BY rank LIMIT ?", (*args, " OR ".join('"' + t + '"' for t in tokens), limit))
        return [row | {"search_method": "FTS5"} for row in result]
    except sqlite3.OperationalError:
        clauses = " OR ".join("c.content LIKE ? ESCAPE '\\'" for _ in tokens)
        result = db.rows(f"SELECT {columns} FROM chunks c JOIN sources s ON s.id=c.source_id WHERE {scope} AND ({clauses}) LIMIT ?", (*args, *("%" + t + "%" for t in tokens), limit))
        return [row | {"search_method": "LIKE fallback — không có xếp hạng ngữ nghĩa"} for row in result]


def chat_context(body, config):
    project = db.one("SELECT * FROM projects WHERE id=?", (body.project_id,))
    base = build_context(config, project, [], body.text, mode=body.mode)
    capacity = config["context"] - config["max_output"] - 160 - sum(token_cost(m["content"], config["model"]) for m in base)
    budget = max(0, int(capacity * 0.72))
    parts, citations = [], []

    def add(part):
        nonlocal budget
        size = token_cost(part, config["model"])
        if size > budget:
            return False
        parts.append(part)
        budget -= size
        return True

    memories = db.rows("SELECT * FROM memories WHERE status='approved' AND (project_id=? OR (project_id IS NULL AND kind IN ('preference','rule'))) ORDER BY CASE WHEN kind='rule' THEN 0 ELSE 1 END,updated_at DESC LIMIT 24", (body.project_id,))
    for memory in memories:
        add(f'Bộ nhớ được duyệt {memory["id"][:8]}, v{memory["version"]}, loại {memory["kind"]}, nguồn {memory["source_label"]}: {memory["content"][:1000]}')
    try:
        from .training import relevant_examples
        for example in relevant_examples(body.text, body.project_id):
            add(f'Ví dụ đã duyệt về cách trả lời (không phải thông số dự án hiện tại):\nNgữ cảnh: {example["context"]}\nHỏi: {example["question"]}\nĐáp án mẫu: {example["answer"]}')
    except ImportError:
        pass
    if body.use_knowledge:
        retrieved = search(body.text, body.project_id, body.source_ids, limit=4)
        for chunk in retrieved:
            label = f"S{len(citations) + 1}"
            excerpt = chunk["content"]
            prefix = f'[{label}] {chunk["filename"]} v{chunk["version"]} / {chunk["location"]} / sha256 {chunk["hash"][:12]}\n'
            while excerpt and token_cost(prefix + excerpt, config["model"]) > budget:
                excerpt = excerpt[:max(0, len(excerpt) - 100)]
            if len(excerpt) < 40:
                continue
            if add(prefix + excerpt):
                citations.append({"label": label, "source_id": chunk["source_id"], "chunk_id": chunk["id"], "filename": chunk["filename"], "version": chunk["version"], "hash": chunk["hash"], "location": chunk["location"], "text": excerpt})
        if not citations:
            add("Không tìm thấy đoạn tài liệu phù hợp trong phạm vi/ngân sách context của lượt này. Không tạo mã [S1] hay nguồn giả.")
    return "\n\n".join(parts), citations


async def index_source(source_id, job_id):
    cancelled = asyncio.Event()
    JOB_CANCEL[job_id] = cancelled
    process, source = None, None
    try:
        source = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
        job = db.one('SELECT status FROM jobs WHERE id=?', (job_id,))
        if not source or not job or job['status'] == 'cancelled':
            return
        db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (db.now(), job_id))
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "app.extract_worker", source["path"], stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=ROOT / "backend", env=os.environ | {"PYTHONUTF8": "1"})
        task = asyncio.create_task(process.communicate())
        async with asyncio.timeout(45):
            while not task.done():
                if cancelled.is_set():
                    raise asyncio.CancelledError
                await asyncio.sleep(0.15)
            output, error = await task
        if cancelled.is_set():
            raise asyncio.CancelledError
        if process.returncode:
            raise ValueError(error.decode("utf-8", errors="replace")[-500:])
        result = json.loads(output)
        if hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() != source['hash']:
            raise ValueError('Tệp đã thay đổi trong khi trích xuất. Lập chỉ mục lại để xác định hash/phiên bản mới.')
        with db.connect() as connection:
            if not connection.execute("SELECT id FROM sources WHERE id=?", (source_id,)).fetchone():
                raise ValueError("Nguồn đã bị xóa")
            connection.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
            for index, chunk in enumerate(result["chunks"]):
                connection.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?)", (db.uid(), source_id, source["project_id"], index, chunk["content"], chunk["location"]))
            connection.execute("UPDATE sources SET status='ready',error=NULL,method=? WHERE id=?", (result["method"], source_id))
            connection.execute("UPDATE jobs SET status='completed',result=?,updated_at=? WHERE id=?", (json.dumps({"chunks": len(result["chunks"])}), db.now(), job_id))
    except asyncio.CancelledError:
        db.execute("UPDATE sources SET status='cancelled' WHERE id=?", (source_id,))
        db.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE id=?", (db.now(), job_id))
    except Exception as error:
        detail = "Trích xuất quá 45 giây" if isinstance(error, TimeoutError) else str(error)[:500]
        db.execute("UPDATE sources SET status='error',error=? WHERE id=?", (detail, source_id))
        db.execute("UPDATE jobs SET status='error',error=?,updated_at=? WHERE id=?", (detail, db.now(), job_id))
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        if source and not db.one('SELECT id FROM sources WHERE id=?', (source_id,)):
            path = Path(source['path']).resolve()
            if path.is_relative_to((DATA / 'knowledge').resolve()):
                path.unlink(missing_ok=True)
        JOB_CANCEL.pop(job_id, None)


def enqueue(source, background):
    if db.one("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('running','queued')")["n"] >= 5:
        raise HTTPException(429, "Hàng đợi đã có 5 công việc. Chờ hoặc hủy bớt.")
    id = db.uid()
    db.execute("INSERT INTO jobs(id,kind,project_id,status,target_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (id, "index", source["project_id"], "queued", source["id"], db.now(), db.now()))
    background.add_task(index_source, source["id"], id)
    return id


@router.get("/sources")
def list_sources(project_id: str = "general"):
    return db.rows("SELECT id,project_id,filename,hash,version,status,error,method,created_at,(SELECT COUNT(*) FROM chunks WHERE source_id=s.id) AS chunk_count FROM sources s WHERE project_id=? ORDER BY created_at DESC", (project_id,))


@router.post("/sources")
async def upload(background: BackgroundTasks, project_id: str = Form(...), file: UploadFile = File(...)):
    from .extract_worker import TEXT_EXTENSIONS
    require_project(project_id)
    filename = Path((file.filename or "document").replace("\\", "/")).name[:180]
    suffix = Path(filename).suffix.lower()
    if suffix not in TEXT_EXTENSIONS | {".pdf", ".docx"}:
        await file.close()
        raise HTTPException(415, "Chỉ nhận PDF text, DOCX, UTF-8 text/Markdown/CSV/mã nguồn.")
    content = await file.read(MAX_UPLOAD + 1)
    await file.close()
    if not content or len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File rỗng hoặc vượt 12 MiB")
    if suffix == ".pdf" and not content.startswith(b"%PDF-") or suffix == ".docx" and not content.startswith(b"PK"):
        raise HTTPException(415, "Nội dung file không khớp định dạng")
    digest = hashlib.sha256(content).hexdigest()
    if existing := db.one("SELECT id FROM sources WHERE project_id=? AND hash=? AND status='ready'", (project_id, digest)):
        return {"id": existing["id"], "duplicate": True}
    id = db.uid()
    path = DATA / "knowledge" / (id + suffix)
    path.write_bytes(content)
    db.execute("INSERT INTO sources(id,project_id,filename,path,hash,status,created_at) VALUES(?,?,?,?,?,?,?)", (id, project_id, filename, str(path), digest, "processing", db.now()))
    try:
        job_id = enqueue({"id": id, "project_id": project_id}, background)
    except HTTPException:
        path.unlink(missing_ok=True)
        db.execute("DELETE FROM sources WHERE id=?", (id,))
        raise
    return {"id": id, "job_id": job_id, "status": "processing"}


@router.get("/sources/{id}")
def source_detail(id: str):
    source = db.one("SELECT id,project_id,filename,hash,version,status,error,method FROM sources WHERE id=?", (id,))
    if not source:
        raise HTTPException(404, "Nguồn không còn hoạt động")
    source["excerpts"] = db.rows("SELECT id,location,content FROM chunks WHERE source_id=? ORDER BY ordinal LIMIT 80", (id,))
    source['excerpts_limited'] = db.one('SELECT COUNT(*) AS n FROM chunks WHERE source_id=?', (id,))['n'] > 80
    return source


@router.post("/sources/{id}/reindex")
def reindex(id: str, background: BackgroundTasks):
    source = db.one("SELECT * FROM sources WHERE id=?", (id,))
    if not source:
        raise HTTPException(404, "Không tìm thấy nguồn")
    if source["status"] == "processing":
        raise HTTPException(409, "Nguồn đang xử lý")
    job_id = enqueue(source, background)
    digest = hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()
    db.execute("UPDATE sources SET status='processing',version=version+1,hash=? WHERE id=?", (digest, id))
    return {"job_id": job_id}


@router.delete("/sources/{id}")
def delete_source(id: str):
    source = db.one("SELECT * FROM sources WHERE id=?", (id,))
    for job in db.rows("SELECT id FROM jobs WHERE target_id=?", (id,)):
        if cancel := JOB_CANCEL.get(job["id"]):
            cancel.set()
    db.execute("DELETE FROM sources WHERE id=?", (id,))
    pending = False
    if source:
        path = Path(source["path"]).resolve()
        if path.is_relative_to((DATA / "knowledge").resolve()):
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                pending = True  # The owned extractor closes it and removes it in finally.
    return {"ok": True, 'file_cleanup_pending': pending, "notice": "Đã loại khỏi index; file bị khóa được dọn sau khi worker đóng. Trích đoạn cũ trong chat/export/backup cần xóa riêng."}


@router.get("/search")
def search_api(q: str, project_id: str = "general"):
    if len(q) > 2000:
        raise HTTPException(422, "Câu tìm kiếm quá dài")
    return search(q, project_id)


@router.get("/jobs")
def jobs(project_id: str = "general"):
    return db.rows("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 30", (project_id,))


@router.post("/jobs/{id}/cancel")
def cancel_job(id: str):
    if cancel := JOB_CANCEL.get(id):
        cancel.set()
    else:
        job = db.one("SELECT * FROM jobs WHERE id=? AND status='queued'", (id,))
        if job:
            db.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE id=?", (db.now(), id))
            db.execute("UPDATE sources SET status='cancelled' WHERE id=?", (job['target_id'],))
    return {"ok": True}


class MemoryInput(StrictModel):
    project_id: str | None = "general"
    kind: str = Field(pattern=r"^(preference|project_fact|research_note|rule)$")
    content: str = Field(min_length=1, max_length=2000)
    source_message_id: str | None = None
    approved: bool = False


def create_memory(body, supersedes=None):
    if body.project_id:
        require_project(body.project_id)
    elif body.kind not in {"preference", "rule"}:
        raise ValueError("Thông số/ghi chú cần gắn một dự án cụ thể")
    if body.source_message_id:
        source = db.one("SELECT m.*,c.project_id FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=?", (body.source_message_id,))
        if not source or body.project_id and source["project_id"] != body.project_id:
            raise ValueError("Nguồn tin nhắn không thuộc phạm vi")
    id, version = db.uid(), 1
    family = id
    with db.connect() as connection:
        if supersedes:
            old = connection.execute("SELECT * FROM memories WHERE id=?", (supersedes,)).fetchone()
            if not old:
                raise HTTPException(404, "Không tìm thấy bộ nhớ")
            if old['project_id'] != body.project_id or old['kind'] != body.kind:
                raise ValueError('Không chuyển scope/loại của cùng một họ bộ nhớ. Tạo bản ghi mới nếu cần phạm vi khác.')
            family = old['family_id'] or old['id']
            latest = connection.execute('SELECT id,version FROM memories WHERE family_id=? ORDER BY version DESC LIMIT 1', (family,)).fetchone()
            supersedes = latest['id']
            version = latest['version'] + 1
            connection.execute("UPDATE memories SET status='superseded',updated_at=? WHERE family_id=? AND status NOT IN ('rejected','superseded')", (db.now(), family))
        connection.execute("INSERT INTO memories(id,project_id,kind,content,status,version,supersedes,source_message_id,source_label,created_at,updated_at,family_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (id, body.project_id, body.kind, body.content, "approved" if body.approved else "pending", version, supersedes, body.source_message_id, "Tin nhắn " + body.source_message_id if body.source_message_id else "Người dùng nhập trực tiếp", db.now(), db.now(), family))
    return db.one("SELECT * FROM memories WHERE id=?", (id,))


@router.get("/memories")
def memories(project_id: str = "general"):
    return db.rows("SELECT a.*,m.content AS source_excerpt FROM memories a LEFT JOIN messages m ON m.id=a.source_message_id WHERE a.project_id=? OR a.project_id IS NULL ORDER BY a.updated_at DESC", (project_id,))


@router.post("/memories")
def add_memory(body: MemoryInput):
    return create_memory(body)


@router.put("/memories/{id}")
def change_memory(id: str, body: MemoryInput):
    return create_memory(body, supersedes=id)


@router.post("/memories/{id}/{action}")
def memory_action(id: str, action: str):
    if action not in {"approve", "reject", "disable"}:
        raise HTTPException(404, "Thao tác không hợp lệ")
    memory = db.one("SELECT * FROM memories WHERE id=?", (id,))
    if not memory:
        raise HTTPException(404, "Không tìm thấy bộ nhớ")
    if memory["status"] == "superseded" and action == "approve":
        raise HTTPException(409, "Bản này đã bị thay thế. Dùng Khôi phục thành phiên bản mới.")
    db.execute("UPDATE memories SET status=?,updated_at=? WHERE id=?", ({"approve": "approved", "reject": "rejected", "disable": "disabled"}[action], db.now(), id))
    return {"ok": True}


@router.delete("/memories/{id}")
def delete_memory(id: str):
    db.execute("DELETE FROM memories WHERE id=?", (id,))
    db.execute('DELETE FROM operations WHERE result LIKE ?', ('%' + id + '%',))
    return {"ok": True, "notice": "Đã loại khỏi retrieval. Nội dung còn trong lịch sử/backup/export phải xử lý riêng."}


class NoteInput(StrictModel):
    project_id: str = "general"
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=50000)
    operation_id: str = Field(min_length=8, max_length=100)


@router.get("/notes")
def notes(project_id: str = "general"):
    return db.rows("SELECT * FROM notes WHERE project_id=? ORDER BY updated_at DESC", (project_id,))


@router.post("/notes")
def add_note(body: NoteInput):
    require_project(body.project_id)
    if old := db.one("SELECT * FROM notes WHERE operation_id=?", (body.operation_id,)):
        if old["project_id"] != body.project_id or old["content"] != body.content or old["title"] != body.title:
            raise HTTPException(409, "Operation ID đã dùng cho nội dung khác")
        return old
    id = db.uid()
    db.execute("INSERT INTO notes VALUES(?,?,?,?,?,?,?,?)", (id, body.project_id, body.title, body.content, 1, body.operation_id, db.now(), db.now()))
    return db.one("SELECT * FROM notes WHERE id=?", (id,))


@router.put("/notes/{id}")
def edit_note(id: str, body: NoteInput):
    old = db.one("SELECT * FROM notes WHERE id=? AND project_id=?", (id, body.project_id))
    if not old:
        raise HTTPException(404, "Không tìm thấy ghi chú trong dự án")
    with db.connect() as connection:
        connection.execute("INSERT INTO note_versions VALUES(?,?,?,?,?)", (db.uid(), id, old["version"], old["content"], db.now()))
        connection.execute("UPDATE notes SET title=?,content=?,version=version+1,updated_at=? WHERE id=?", (body.title, body.content, db.now(), id))
    return db.one("SELECT * FROM notes WHERE id=?", (id,))


@router.get("/notes/{id}/versions")
def note_versions(id: str):
    return db.rows("SELECT * FROM note_versions WHERE note_id=? ORDER BY version DESC", (id,))


@router.get("/notes/{id}/export")
def export_note(id: str):
    note = db.one("SELECT * FROM notes WHERE id=?", (id,))
    if not note:
        raise HTTPException(404, "Không tìm thấy ghi chú")
    return PlainTextResponse(f'# {note["title"]}\n\n{note["content"]}\n\n---\nD-bot · v{note["version"]} · {note["updated_at"]}\n', headers={"Content-Disposition": f'attachment; filename="note-{id}.md"'})


@router.delete("/notes/{id}")
def delete_note(id: str):
    db.execute("DELETE FROM notes WHERE id=?", (id,))
    db.execute('DELETE FROM operations WHERE result LIKE ?', ('%' + id + '%',))
    return {"ok": True}

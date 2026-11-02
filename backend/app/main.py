import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from importlib.util import find_spec

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import db, ollama
from .chat import RUNNING, chat_response
from .config import ORIGINS, ROOT, DATA, STT_PATH, STT_LEARNING_PATH, TTS_PATH
from .schemas import ConversationUpdate, AppSettings, ChatInput, ConversationCreate, ProjectCreate

TOKEN = secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app):
    db.migrate()
    yield
    for cancel in list(RUNNING.values()):
        cancel.set()
    from .voice_runtime import runtime
    await runtime.close()
    from .coding_agent import ACTIVE
    for cancel,workspace_id in list(ACTIVE.values()):cancel.set()


app = FastAPI(title="D-bot local API", version="0.1.0", lifespan=lifespan, telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False, "auto_configure": False})
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])


@app.middleware("http")
async def local_security(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in ORIGINS or request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"code": "ORIGIN_DENIED", "detail": "Chỉ cho phép giao diện localhost đã cấu hình."}, status_code=403)
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(request.headers.get("x-d-bot-token", ""), TOKEN):
            return JSONResponse({"code": "SESSION_REQUIRED", "detail": "Phiên local đã đổi. Tải lại trang."}, status_code=403)
        length = request.headers.get("content-length")
        limit = (128 if request.url.path == '/api/data/import' else 16) * 1024 * 1024
        if length and (not length.isdigit() or int(length) > limit):
            return JSONResponse({"code": "TOO_LARGE", "detail": "Yêu cầu vượt giới hạn upload."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def value_error(request, error):
    return JSONResponse({"code": "INVALID_INPUT", "detail": str(error)}, status_code=422)


@app.get("/api/session")
def session():
    return {"token": TOKEN}


@app.get("/api/health")
async def health():
    info = await ollama.diagnostics()
    config = db.settings()
    stt_missing = [name for name in ['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'] if not (STT_PATH / name).exists()]
    if find_spec('faster_whisper') is None:
        stt_missing.append('dependency faster-whisper')
    tts_missing = [str(path.name) for path in [TTS_PATH, Path(str(TTS_PATH) + '.json')] if not path.exists()]
    if find_spec('piper') is None:
        tts_missing.append('dependency piper-tts')
    return {"backend": True, "database": bool(db.one("SELECT 1 AS ok")), "llm": info,
            "model": config["model"], "model_ready": any(m["name"] == config["model"] for m in info["models"]),
            "offline": config["offline"], "cloud_disabled": "Launcher cần xác nhận OLLAMA_NO_CLOUD=1 trong log Ollama.",
            "stt": not stt_missing, "tts": not tts_missing, 'voice_missing': {'stt': stt_missing, 'tts': tts_missing},
            'offline_readiness': {'runtime_loopback_only': True, 'model_assets_ready': any(m['name'] == config['model'] for m in info['models']) and not stt_missing and not tts_missing, 'internet_disconnection_tested': False},
            'language_voice':{'stt_learning_model':STT_LEARNING_PATH.name,'stt_learning_ready':all((STT_LEARNING_PATH/name).exists() for name in ['model.bin','config.json','tokenizer.json','vocabulary.txt']),'tts_en_ja_ready':find_spec('kokoro_onnx') is not None and all((DATA/'models/kokoro'/name).exists() for name in ['kokoro-v1.0.onnx','voices-v1.0.bin'])},
            "queue": len(RUNNING), "heavy_busy": ollama.HEAVY_LOCK.locked()}


@app.get("/api/models")
async def models():
    return await ollama.diagnostics()


@app.get("/api/models/info")
async def info(model: str):
    try:
        return await ollama.model_info(model)
    except Exception as error:
        raise HTTPException(503, str(error)[:300])


@app.get("/api/settings")
def get_settings():
    return db.settings()


@app.put("/api/settings")
def save_settings(body: AppSettings):
    for root in body.allowed_roots:
        try:
            path = Path(root).resolve(strict=True)
        except OSError:
            raise ValueError('Thư mục được cấp quyền không tồn tại hoặc không truy cập được: ' + root)
        if not path.is_dir() or str(path).startswith("\\\\") or path == Path(path.anchor):
            raise ValueError("Chỉ cấp một thư mục cụ thể, không phải ổ đĩa/UNC.")
    db.execute("INSERT OR REPLACE INTO settings VALUES('app',?)", (body.model_dump_json(),))
    return body


@app.get("/api/projects")
def projects():
    return db.rows("SELECT p.*,(SELECT COUNT(*) FROM conversations c WHERE c.project_id=p.id) AS conversation_count FROM projects p ORDER BY p.created_at")


@app.post("/api/projects")
def create_project(body: ProjectCreate):
    id = db.uid()
    db.execute("INSERT INTO projects VALUES(?,?,?,?)", (id, body.name, body.description, db.now()))
    return db.one("SELECT * FROM projects WHERE id=?", (id,))


@app.put("/api/projects/{id}")
def edit_project(id: str, body: ProjectCreate):
    require_project(id)
    db.execute("UPDATE projects SET name=?,description=? WHERE id=?", (body.name, body.description, id))
    return {"ok": True}


def require_project(id):
    if not db.one("SELECT id FROM projects WHERE id=?", (id,)):
        raise HTTPException(404, "Không tìm thấy dự án")


@app.get("/api/conversations")
def conversations(project_id: str = "general", all_projects: bool = False):
    if all_projects:
        return db.rows("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 500")
    require_project(project_id)
    return db.rows("SELECT * FROM conversations WHERE project_id=? ORDER BY updated_at DESC LIMIT 200", (project_id,))


@app.post("/api/conversations")
def create_conversation(body: ConversationCreate):
    require_project(body.project_id)
    id = db.uid()
    db.execute("INSERT INTO conversations VALUES(?,?,?,?,?)", (id, body.project_id, body.title, db.now(), db.now()))
    return {"id": id}


@app.put("/api/conversations/{id}")
def update_conversation(id: str, body: ConversationUpdate):
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM conversations WHERE id=?", (id,)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy hội thoại")
        if body.title is None and body.project_id is None:
            raise HTTPException(422, "Cần tên mới hoặc dự án đích")
        if connection.execute("SELECT id FROM messages WHERE conversation_id=? AND status='running' LIMIT 1", (id,)).fetchone():
            raise HTTPException(409, "Đợi lượt trả lời hoàn tất trước khi sắp xếp hội thoại")
        project = body.project_id or row['project_id']
        if not connection.execute("SELECT id FROM projects WHERE id=?", (project,)).fetchone():
            raise HTTPException(404, "Không tìm thấy dự án đích")
        connection.execute("UPDATE conversations SET title=?,project_id=?,updated_at=? WHERE id=?", (body.title or row['title'], project, db.now(), id))
    return db.one("SELECT * FROM conversations WHERE id=?", (id,))


@app.get("/api/conversations/{id}/messages")
def messages(id: str):
    result = db.rows("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (id,))
    for message in result:
        message['citations'] = []
        for citation in json.loads(message['metadata']).get('citations', []):
            source = db.one('SELECT hash,version,status FROM sources WHERE id=?', (citation['source_id'],))
            message['citations'].append(citation | {'active': bool(source and source['status'] == 'ready' and source['hash'] == citation['hash'] and source['version'] == citation['version'])})
    return result


@app.delete("/api/conversations/{id}")
def delete_conversation(id: str):
    db.execute("DELETE FROM conversations WHERE id=?", (id,))
    return {"ok": True}


@app.post("/api/chat")
async def chat(body: ChatInput, request: Request):
    return await chat_response(body, request)


@app.post("/api/chat/{request_id}/cancel")
def cancel(request_id: str):
    if event := RUNNING.get(request_id):
        event.set()
    return {"ok": True}


from .voice import router as voice_router
app.include_router(voice_router)
from .desktop import router as desktop_router
app.include_router(desktop_router)
from .research import router as research_router
from .tools import router as tools_router
app.include_router(research_router)
app.include_router(tools_router)
from .training import router as training_router
app.include_router(training_router)
from .data_control import router as data_router
app.include_router(data_router)
from .projects import router as project_router
app.include_router(project_router)
from .personalization import router as profile_router
app.include_router(profile_router)
from .careers import router as careers_router
app.include_router(careers_router)
from .career_review import router as career_review_router
app.include_router(career_review_router)
from .coding import router as coding_router
from . import coding_templates, coding_agent
app.include_router(coding_router)
from .language_learning import router as language_router
app.include_router(language_router)

BUILD = ROOT / "frontend" / "dist"
if BUILD.exists():
    app.mount("/", StaticFiles(directory=BUILD, html=True), name="frontend")

import ast
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import time
import sys
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError

from . import db
from .config import ROOT
from .extract_worker import TEXT_EXTENSIONS
from .research import MemoryInput, NoteInput, add_note, change_memory, create_memory, delete_memory, edit_note, search, source_detail
from .schemas import StrictModel

router = APIRouter(prefix="/api/tools", tags=["tools"])
TOOL_SLOTS = asyncio.Semaphore(2)


class Calculate(StrictModel):
    expression: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="", max_length=30)


def calculate(body):
    tree = ast.parse(body.expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 60:
        raise ValueError("Biểu thức quá phức tạp")
    def visit(node, depth=0):
        if depth > 12:
            raise ValueError("Biểu thức lồng quá sâu")
        if isinstance(node, ast.Expression):
            return visit(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in {int, float} and abs(node.value) <= 1e12:
            result = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            result = visit(node.operand, depth + 1) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp):
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add): result = left + right
            elif isinstance(node.op, ast.Sub): result = left - right
            elif isinstance(node.op, ast.Mult): result = left * right
            elif isinstance(node.op, ast.Div): result = left / right
            elif isinstance(node.op, ast.FloorDiv): result = left // right
            elif isinstance(node.op, ast.Mod): result = left % right
            elif isinstance(node.op, ast.Pow) and abs(right) <= 12: result = left ** right
            else: raise ValueError("Toán tử không được phép; số mũ tối đa 12")
        else:
            raise ValueError("Chỉ nhận số và + - * / // % **; không gọi hàm/mã lệnh")
        if type(result) not in {int, float} or not math.isfinite(result) or abs(result) > 1e100:
            raise ValueError("Kết quả vượt giới hạn số thực")
        return result
    try:
        return {"value": visit(tree), "unit": body.unit, "notice": "Đơn vị là nhãn bạn cung cấp; chưa có kiểm tra thứ nguyên."}
    except (ZeroDivisionError, OverflowError, SyntaxError):
        raise ValueError("Biểu thức lỗi, chia 0 hoặc vượt giới hạn")


def resolve_allowed(path):
    if path.startswith(("\\\\", "//")) or ":" in path[2:]:
        raise ValueError("Không cho phép UNC/device path/alternate data stream")
    candidate = Path(path).resolve(strict=True)
    roots = [Path(root).resolve(strict=True) for root in db.settings()["allowed_roots"]]
    if not any(candidate.is_relative_to(root) for root in roots):
        raise ValueError("Đường dẫn ngoài thư mục đã cấp quyền (đã resolve symlink/junction)")
    return candidate


class FileRead(StrictModel):
    path: str = Field(min_length=1, max_length=1000)
    start_line: int = Field(default=1, ge=1, le=100000)
    lines: int = Field(default=80, ge=1, le=200)


def read_file(body):
    path = resolve_allowed(body.path)
    if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS or path.name.startswith(".env") or path.stat().st_size > 512000:
        raise ValueError("Chỉ đọc file UTF-8 text/mã nguồn <= 500 KiB; không đọc .env")
    content = path.read_text(encoding="utf-8-sig")
    if "\x00" in content:
        raise ValueError("Không đọc file nhị phân")
    lines = content.splitlines()
    return {"path": str(path), "start_line": body.start_line, "content": "\n".join(lines[body.start_line - 1:body.start_line + body.lines - 1]), "total_lines": len(lines)}


class FileSearch(StrictModel):
    root: str = Field(min_length=1, max_length=1000)
    query: str = Field(min_length=1, max_length=100)


def search_files(body):
    root = resolve_allowed(body.root)
    if not root.is_dir():
        raise ValueError("Cần đường dẫn thư mục")
    results, visited = [], 0
    started = time.monotonic()
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [d for d in directories if d not in {".git", "node_modules", ".venv", ".runtime", "__pycache__"} and not (Path(current) / d).is_symlink() and not (Path(current) / d).is_junction()]
        for name in files:
            visited += 1
            if visited > 10000 or time.monotonic() - started > 5:
                return {"files": results, "limited": True}
            if body.query.casefold() in name.casefold():
                try:
                    candidate = resolve_allowed(str(Path(current) / name))
                    results.append({"path": str(candidate), "bytes": candidate.stat().st_size})
                except (ValueError, OSError):
                    continue
                if len(results) >= 100:
                    return {"files": results, "limited": True}
    return {"files": results, "limited": False}


class KnowledgeSearch(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    project_id: str = "general"


class SourceRead(StrictModel):
    source_id: str
    project_id: str = "general"


def read_source(body):
    source = source_detail(body.source_id)
    if source["project_id"] != body.project_id:
        raise ValueError("Nguồn không thuộc dự án")
    return source


class NoteUpdate(NoteInput):
    note_id: str


class MemoryManage(MemoryInput):
    action: Literal["create", "update", "delete"] = "create"
    memory_id: str | None = None


def manage_memory(body):
    data = MemoryInput(**body.model_dump(exclude={"action", "memory_id"}))
    if body.action == "create":
        return create_memory(data)
    old = db.one("SELECT * FROM memories WHERE id=? AND project_id IS ?", (body.memory_id, body.project_id))
    if not old:
        raise ValueError("Bộ nhớ không thuộc phạm vi")
    if body.action == "update":
        return change_memory(body.memory_id, data)
    return delete_memory(body.memory_id)


REGISTRY = {
    "calculate": (Calculate, calculate, "Tính số học giới hạn bằng AST; không thực thi mã.", "numeric"),
    "search_knowledge": (KnowledgeSearch, lambda b: search(b.query, b.project_id), "Tìm đoạn tài liệu đúng dự án.", "project-read"),
    "read_source_excerpt": (SourceRead, read_source, "Đọc nguồn đã nhập theo ID và dự án.", "project-read"),
    "read_project_file": (FileRead, read_file, "Đọc file trong allowlist đã resolve.", "allowlist-read"),
    "search_project_files": (FileSearch, search_files, "Tìm theo tên trong thư mục đã cấp quyền.", "allowlist-read"),
    "create_research_note": (NoteInput, add_note, "Tạo ghi chú DB thật, có operation ID chống lặp.", "project-write"),
    "update_research_note": (NoteUpdate, lambda b: edit_note(b.note_id, NoteInput(**b.model_dump(exclude={"note_id"}))), "Cập nhật note và giữ bản cũ.", "project-write"),
    "manage_memory": (MemoryManage, manage_memory, "Lưu/sửa/xóa bộ nhớ theo chỉ dẫn rõ của người dùng.", "project-write"),
}


class ToolCall(StrictModel):
    arguments: dict
    operation_id: str = Field(min_length=8, max_length=100)


@router.get("")
def list_tools():
    return {"automatic_tool_calling": 'calculate only after digest probe', "notice": "Đọc/ghi qua UI rõ ràng; chat chỉ tự dùng calculate trên model đã probe.", "tools": [{"name": name, "description": info[2], "schema": info[0].model_json_schema(), "scope": info[3], "timeout_seconds": 25 if info[3].endswith('write') else 8} for name, info in REGISTRY.items()]}


def execute_tool(name: str, body: ToolCall):
    if name not in REGISTRY:
        raise HTTPException(404, "Công cụ không được cấp quyền")
    schema, handler, description, scope = REGISTRY[name]
    project_id = body.arguments.get("project_id")
    status = "error"
    try:
        input_hash = hashlib.sha256(json.dumps(body.arguments, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if previous := db.one('SELECT * FROM operations WHERE id=?', (body.operation_id,)):
            if previous['tool'] != name or previous['input_hash'] != input_hash:
                raise ValueError('Operation ID đã dùng cho công cụ/nội dung khác')
            status = 'completed'
            return json.loads(previous['result'])
        arguments = schema.model_validate(body.arguments)
        result = handler(arguments)
        status = "completed"
        response = {"tool": name, "operation_id": body.operation_id, "status": status, "result": result}
        if scope.endswith('write'):
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?)', (body.operation_id, name, input_hash, json.dumps(response, ensure_ascii=False), db.now()))
        return response
    except (ValidationError, ValueError, OSError, SyntaxError) as error:
        raise HTTPException(422, str(error)[:500])
    finally:
        db.execute("INSERT INTO tool_audit VALUES(?,?,?,?,?,?)", (db.uid(), name, project_id, status, body.operation_id, db.now()))


@router.post('/{name}')
async def run_tool(name: str, body: ToolCall, request: Request):
    if name not in REGISTRY:
        raise HTTPException(404, 'Công cụ không được cấp quyền')
    schema, handler, description, scope = REGISTRY[name]
    try:
        schema.model_validate(body.arguments)
    except ValidationError as error:
        raise HTTPException(422, str(error)[:500])
    process, task, startup_task = None, None, None
    timeout = 25 if scope.endswith('write') else 8
    phase, startup_seconds, acquired = 'queue', 0.0, False
    try:
        async with asyncio.timeout(timeout):
            await TOOL_SLOTS.acquire()
        acquired = True
        phase = 'startup'
        started = time.monotonic()
        async with asyncio.timeout(30):
            env = os.environ | {'DBOT_DATABASE_PATH': str(db.DB_PATH), 'PYTHONUTF8': '1'}
            process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'app.tool_worker', name, '--ready-signal', stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=ROOT / 'backend', env=env)
            startup_task = asyncio.create_task(process.stdout.readline())
            while not startup_task.done():
                if await request.is_disconnected():
                    raise HTTPException(499, 'Đã hủy khởi động công cụ')
                await asyncio.sleep(.1)
            ready = await startup_task
            if ready.strip() != b'{"ready":true}':
                raise HTTPException(422, 'Worker không khởi động đúng giao thức')
        startup_seconds = time.monotonic() - started
        phase = 'execution'
        async with asyncio.timeout(timeout):
            task = asyncio.create_task(process.communicate(body.model_dump_json().encode()))
            while not task.done():
                if await request.is_disconnected():
                    raise HTTPException(499, 'Đã hủy công cụ. Retry cùng operation ID để kiểm tra biên nhận nếu cần.')
                await asyncio.sleep(.1)
            output, error = await task
            if process.returncode:
                raise HTTPException(422, error.decode('utf-8', errors='replace')[-500:])
            result = json.loads(output)
            if result['http_status'] != 200:
                raise HTTPException(result['http_status'], result['detail'])
            return result['result']
    except TimeoutError:
        message = 'Worker chưa khởi động sau 30 giây.' if phase=='startup' else f'Công cụ vượt {timeout} giây '+('trong hàng chờ.' if phase=='queue' else 'khi thực thi.')
        raise HTTPException(504, message+' Worker đã dừng; retry cùng operation ID để kiểm tra biên nhận nếu cần.', headers={'X-Worker-Startup-Seconds':str(round(startup_seconds,3))})
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        for pending in (task, startup_task):
            if pending and not pending.done():
                pending.cancel()
        if acquired:
            TOOL_SLOTS.release()

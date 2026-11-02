"""Consistent backup and validated restore into a NEW data directory."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import zipfile
from contextlib import closing

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import db
from .config import DATA
from .schemas import AppSettings

router = APIRouter(prefix="/api/data", tags=["data"])
MAX_BUNDLE = 128 * 1024 * 1024


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def schema(connection):
    return {row[0]: re.sub(r"\s+", " ", row[1] or "").strip() for row in connection.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")}


@router.post("/backup")
def backup():
    id = db.uid()
    snapshot = DATA / "backups" / (id + ".sqlite3")
    archive_path = DATA / "backups" / (id + ".zip")
    partial = archive_path.with_suffix(".part")
    try:
        with closing(sqlite3.connect(db.DB_PATH, timeout=15)) as source, closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError("SQLite integrity: " + integrity)
            sources = destination.execute("SELECT id,path,hash FROM sources").fetchall()
        manifest = {"schema_version": 1, "kind": "D-bot-local-backup", "created_at": db.now(), "id": id, "files": {"database.sqlite3": file_hash(snapshot)}, "sources": {}, "notice": "Không gồm raw audio/model/dataset snapshots. Giữ riêng các dataset đã xuất nếu cần."}
        total = snapshot.stat().st_size
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "database.sqlite3")
            for source_id, source_path, expected in sources:
                path = Path(source_path).resolve(strict=True)
                if not path.is_relative_to((DATA / "knowledge").resolve()) or file_hash(path) != expected:
                    raise ValueError("Nguồn thay đổi/không hợp lệ khi backup. Thử lại sau khi công việc nhập đã xong.")
                total += path.stat().st_size
                if total > MAX_BUNDLE:
                    raise ValueError("Backup vượt 128 MiB. V1 cần chia nhỏ dữ liệu trước khi xuất.")
                name = "knowledge/" + path.name
                manifest["files"][name] = expected
                manifest["sources"][source_id] = name
                archive.write(path, name)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        partial.replace(archive_path)
        return {"id": id, "integrity": integrity, "bytes": archive_path.stat().st_size}
    finally:
        snapshot.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)


@router.get("/backups")
def backups():
    return [{"id": path.stem, "bytes": path.stat().st_size} for path in sorted((DATA / "backups").glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)]


def backup_file(id):
    if not re.fullmatch(r"[a-f0-9-]{36}", id):
        raise HTTPException(404, "ID backup không hợp lệ")
    path = DATA / "backups" / (id + ".zip")
    if not path.exists():
        raise HTTPException(404, "Không tìm thấy backup")
    return path


@router.get("/backups/{id}")
def download_backup(id: str):
    return FileResponse(backup_file(id), filename=f"D-bot-backup-{id}.zip")


@router.delete("/backups/{id}")
def remove_backup(id: str):
    backup_file(id).unlink()
    return {"ok": True}


@router.post("/import")
async def import_backup(file: UploadFile = File(...)):
    raw = await file.read(MAX_BUNDLE + 1)
    await file.close()
    if len(raw) > MAX_BUNDLE:
        raise HTTPException(413, "Backup vượt 128 MiB")
    target = DATA.parent / ("restored-" + db.uid())
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000 or sum(item.file_size for item in infos) > MAX_BUNDLE:
                raise ValueError("Archive vượt giới hạn giải nén")
            names = [item.filename for item in infos]
            if len(set(names)) != len(names) or any(not re.fullmatch(r"(?:manifest\.json|database\.sqlite3|knowledge/[a-f0-9-]{36}\.[A-Za-z0-9]+)", name) for name in names):
                raise ValueError("Archive có tên file không hợp lệ/path traversal/file trùng")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("schema_version") != 1 or manifest.get("kind") != "D-bot-local-backup":
                raise ValueError("Manifest backup không được hỗ trợ")
            if set(names) != {"manifest.json", *manifest["files"]}:
                raise ValueError("Manifest và danh sách file không khớp")
            target.mkdir(exist_ok=False)
            (target / "database").mkdir()
            (target / "knowledge").mkdir()
            for name, expected in manifest["files"].items():
                content = archive.read(name)
                if hashlib.sha256(content).hexdigest() != expected:
                    raise ValueError("Hash không khớp: " + name)
                output = target / ("database/d_bot.sqlite3" if name == "database.sqlite3" else name)
                output.write_bytes(content)
        imported = target / "database" / "d_bot.sqlite3"
        with closing(sqlite3.connect(imported)) as connection, connection, closing(sqlite3.connect(db.DB_PATH)) as current:
            connection.execute("PRAGMA trusted_schema=OFF")
            expected, actual = schema(current), schema(connection)
            groups={'careers_schema.sql':{'career_applications','career_events','career_events_application'},'coding_schema.sql':{'coding_workspaces','coding_batches','coding_runs','coding_audit','coding_runs_workspace','coding_audit_workspace'},'career_review_schema.sql':{'career_reviews'}}
            groups['language_schema.sql']={'language_profiles','language_attempts','ix_language_attempts'}
            missing={name:objects for name,objects in groups.items() if not objects.intersection(actual)}
            absent=set().union(*missing.values()) if missing else set()
            # Only exact additive local schemas may be missing, never arbitrary SQL.
            if missing and actual=={key:value for key,value in expected.items() if key not in absent}:
                for name in missing:connection.executescript(Path(__file__).with_name(name).read_text(encoding='utf-8'))
                actual=schema(connection)
            if actual != expected:
                raise ValueError("Schema backup khác phiên bản ứng dụng hoặc có object SQL lạ")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Database backup không toàn vẹn")
            for table in ("projects", "conversations", "messages", "sources", "chunks", "memories", "notes", "feedback", "approved_examples",'career_applications','career_events','coding_workspaces','coding_batches','coding_runs','coding_audit'):
                if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", row[0]) for row in connection.execute(f"SELECT id FROM {table}")):
                    raise ValueError("ID thực thể không hợp lệ")
            source_rows = connection.execute("SELECT id FROM sources").fetchall()
            if {row[0] for row in source_rows} != set(manifest["sources"]):
                raise ValueError("Backup thiếu nguồn tài liệu")
            for (source_id,) in source_rows:
                name = manifest["sources"][source_id]
                if name not in manifest["files"] or not name.startswith("knowledge/"):
                    raise ValueError("Ánh xạ tài liệu không hợp lệ")
                connection.execute("UPDATE sources SET path=? WHERE id=?", (str(target / name), source_id))
            setting = connection.execute("SELECT value FROM settings WHERE key='app'").fetchone()
            if setting:
                restored = AppSettings.model_validate_json(setting[0])
                restored.allowed_roots = []
                restored.offline = True
                connection.execute("UPDATE settings SET value=? WHERE key='app'", (restored.model_dump_json(),))
            # Exports have independent lifecycle and are deliberately not in this bundle.
            connection.execute("DELETE FROM training_exports")
            connection.execute('UPDATE coding_workspaces SET enabled=0')
        return {"ok": True, "path": str(target), "notice": f"Đã phục hồi vào {target}. Chưa thay phiên đang chạy. Dừng app, đặt DBOT_DATA_DIR trong .env thành thư mục này rồi khởi động lại. Model/voice chưa nằm trong backup; cấu hình STT_MODEL_PATH/TTS_VOICE_PATH về các model đã tải. Allowlist được xóa để bạn cấp lại."}
    except (ValueError, KeyError, zipfile.BadZipFile, sqlite3.DatabaseError, OSError) as error:
        if target.exists():
            # Target is an absolute fresh UUID directory under DATA.parent, never active DATA.
            checked = target.resolve()
            if checked.parent == DATA.parent.resolve() and checked.name.startswith("restored-"):
                shutil.rmtree(checked)
        raise HTTPException(422, str(error)[:500])

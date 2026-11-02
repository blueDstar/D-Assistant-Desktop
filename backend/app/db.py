import json
import os
import sqlite3
import uuid
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from .config import DATA, DEFAULTS

DB_PATH = Path(os.getenv('DBOT_DATABASE_PATH', str(DATA / 'database' / 'd_bot.sqlite3')))
_TRANSACTION = ContextVar('d_bot_transaction', default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


@contextmanager
def connect():
    current = _TRANSACTION.get()
    if current is not None:
        yield current
        return
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=15000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def transaction():
    """Nested services share one atomic transaction for effects and receipts."""
    with connect() as connection:
        token = _TRANSACTION.set(connection)
        try:
            yield connection
        finally:
            _TRANSACTION.reset(token)


def rows(sql, args=()):
    with connect() as db:
        return [dict(row) for row in db.execute(sql, args).fetchall()]


def one(sql, args=()):
    result = rows(sql, args)
    return result[0] if result else None


def execute(sql, args=()):
    with connect() as db:
        db.execute(sql, args)


def settings():
    value = one("SELECT value FROM settings WHERE key='app'")
    return DEFAULTS | (json.loads(value["value"]) if value else {})


def migrate():
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript('''
        CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,role TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'text',request_id TEXT,metadata TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,no_learning INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS ix_messages_conversation ON messages(conversation_id,created_at);
        CREATE INDEX IF NOT EXISTS ix_conversations_project ON conversations(project_id,updated_at);
        ''')
        db.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,?)", ("general", "Không gian chung", "Chưa gắn với dự án cụ thể", now()))
        db.execute("INSERT OR IGNORE INTO migrations VALUES(1,?)", (now(),))
        # A process crash must never leave a persisted answer labelled 'running'.
        db.execute("UPDATE messages SET status='interrupted' WHERE status='running'")
        db.executescript(Path(__file__).with_name("research_schema.sql").read_text(encoding="utf-8"))
        if 'family_id' not in {row['name'] for row in db.execute('PRAGMA table_info(memories)')}:
            db.execute("ALTER TABLE memories ADD COLUMN family_id TEXT")
            db.execute("UPDATE memories SET family_id=id WHERE family_id IS NULL")
        db.executescript(Path(__file__).with_name("training_schema.sql").read_text(encoding="utf-8"))
        db.executescript(Path(__file__).with_name('careers_schema.sql').read_text(encoding='utf-8'))
        db.executescript(Path(__file__).with_name('career_review_schema.sql').read_text(encoding='utf-8'))
        db.executescript(Path(__file__).with_name('coding_schema.sql').read_text(encoding='utf-8'))
        db.executescript(Path(__file__).with_name('language_schema.sql').read_text(encoding='utf-8'))
        db.execute("UPDATE coding_batches SET status='interrupted',error='Ứng dụng khởi động lại trong lúc ghi; kiểm tra và Khôi phục.' WHERE status='applying'")
        db.execute("UPDATE coding_runs SET status='interrupted',error='Ứng dụng đã khởi động lại' WHERE status IN ('queued','running')")
        db.execute("UPDATE evaluations SET status='interrupted' WHERE status IN ('queued','running')")
        db.execute("UPDATE jobs SET status='interrupted',error='Ứng dụng đã khởi động lại' WHERE status IN ('queued','running')")
        try:
            db.executescript('''
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content,content='chunks',content_rowid='rowid',tokenize='unicode61 remove_diacritics 2');
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunks_fts(rowid,content) VALUES(new.rowid,new.content); END;
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO chunks_fts(chunks_fts,rowid,content) VALUES('delete',old.rowid,old.content); END;
            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN INSERT INTO chunks_fts(chunks_fts,rowid,content) VALUES('delete',old.rowid,old.content); INSERT INTO chunks_fts(rowid,content) VALUES(new.rowid,new.content); END;
            ''')
        except sqlite3.OperationalError:
            # Search service explicitly reports LIKE fallback if FTS5 is unavailable.
            pass

CREATE TABLE IF NOT EXISTS coding_workspaces(
 id TEXT PRIMARY KEY, root TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_batches(
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES coding_workspaces(id),
 source TEXT NOT NULL, summary TEXT NOT NULL, status TEXT NOT NULL,
 files TEXT NOT NULL, created_dirs TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_runs(
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES coding_workspaces(id),
 task TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
 batch_id TEXT REFERENCES coding_batches(id), answer TEXT NOT NULL DEFAULT '',
 error TEXT NOT NULL DEFAULT '', events TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_audit(
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES coding_workspaces(id),
 event TEXT NOT NULL, reference_id TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS coding_runs_workspace ON coding_runs(workspace_id,created_at);
CREATE INDEX IF NOT EXISTS coding_audit_workspace ON coding_audit(workspace_id,created_at);

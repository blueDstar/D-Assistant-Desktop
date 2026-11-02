CREATE TABLE IF NOT EXISTS language_profiles(project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,language TEXT NOT NULL,profile TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(project_id,language));
CREATE TABLE IF NOT EXISTS language_attempts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,language TEXT NOT NULL,question_id TEXT NOT NULL,choice INTEGER NOT NULL,correct INTEGER NOT NULL,topic TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_language_attempts ON language_attempts(project_id,language,created_at);

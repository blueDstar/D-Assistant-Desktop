CREATE TABLE IF NOT EXISTS career_applications(
 id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
 company TEXT NOT NULL, role TEXT NOT NULL, location TEXT NOT NULL DEFAULT '',
 job_url TEXT NOT NULL, recipient TEXT NOT NULL DEFAULT '', salary TEXT NOT NULL DEFAULT '',
 fit TEXT NOT NULL DEFAULT '', concerns TEXT NOT NULL DEFAULT '',
 stage TEXT NOT NULL DEFAULT 'researching', reason TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS career_events(
 id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES career_applications(id) ON DELETE CASCADE,
 operation_id TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, source TEXT NOT NULL,
 occurred_at TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS career_events_application ON career_events(application_id,occurred_at);

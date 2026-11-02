CREATE TABLE IF NOT EXISTS career_reviews(
 application_id TEXT PRIMARY KEY REFERENCES career_applications(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, posting TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', approval_hash TEXT NOT NULL DEFAULT '',
 reviewed_at TEXT, review_note TEXT NOT NULL DEFAULT '', plan TEXT,
 updated_at TEXT NOT NULL
);

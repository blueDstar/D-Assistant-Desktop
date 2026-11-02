# Contributor instructions

- Preserve user data; never commit .env, data/, backups, chats, CVs, credentials or model weights.
- Keep inference and the backend on loopback. Do not add cloud fallbacks silently.
- File access requires an explicit allowed root. Model edits require reviewed diffs and hash guards.
- Recruitment: approve each specific job description before drafting, scheduling or sending. Never withdraw an existing application automatically.
- Distinguish mocked tests from real model, microphone and desktop checks. Do not claim weight training without a trainer and evaluation.
- Run checks relevant to your change. See docs/DEVELOPMENT.md.

# Chatisfying · klartext

A modern messenger with private chats, group chats, invitations and group roles.
The interface is English; "klartext" is the small German second name under the logo.

- **Frontend:** plain HTML, CSS and JavaScript (ES modules) → GitHub Pages
- **Backend:** Python + Flask, data in JSON files → a separate Python server
- **Talking to each other:** REST API with JSON, login via `Authorization: Bearer <token>`

## Run it locally

```bash
# 1) Backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit ADMIN_USERNAME etc.
python app.py                                          # http://127.0.0.1:5000

# 2) Frontend (second terminal) – must be served over http, not opened as a file
cd frontend
python -m http.server 8000                             # http://127.0.0.1:8000/login.html
```

Without SMTP settings the verification code is **printed in the backend terminal** (dev mode).

## First steps

1. In `.env` set `ADMIN_USERNAME=yourname`. That name may always register and becomes global admin.
2. Open `login.html` → *Create account* → register with that name → code from the terminal.
3. As admin open **Admin → Whitelist** and add the usernames of your friends.
4. Friends register themselves; you approve them under **Admin → Users**.

## Deploy

- Frontend: put the `frontend/` folder on GitHub Pages and set `API_URL` in `frontend/config.js`.
- Backend: run on a server with HTTPS, e.g. `pip install waitress && waitress-serve --threads=8 app:app`.
  Use **one process only** (the JSON file lock lives inside one process).
- In `.env` set `ALLOWED_ORIGINS=https://YOURNAME.github.io` so the browser may call the API.
- Never commit `backend/.env` or `backend/data/*.json` (see `.gitignore`): they hold secrets and passwords hashes.

## Where is what

| File | Job |
|---|---|
| `backend/storage.py` | Atomic, locked JSON read/write, `transaction()` |
| `backend/security.py` | Validation, password hashes, login tokens, permission decorators, rate limit |
| `backend/auth.py` | Registration (whitelist → email code → password → admin approval), login, logout |
| `backend/users.py` / `messages.py` | Profiles, user search / private messages |
| `backend/groups.py` / `invitations.py` | Groups, roles, group messages / invitations |
| `backend/admin.py` | Approve or suspend users, whitelist, delete groups |
| `backend/mailer.py` | Sends the code (named `mailer`, not `email`, because Python already has an `email` package) |
| `frontend/api.js` | The only place that calls the backend |
| `frontend/ui.js`, `chatpane.js` | Shared UI helpers and the message pane used by chats and groups |
| `frontend/pages/*.js` | One file per page |

## Security notes

- Passwords are stored as salted hashes; codes expire after 10 minutes and allow 5 attempts.
- Every permission is checked on the server. Logout, password change and suspension invalidate old tokens.
- Tokens are sent in a header, not in cookies, so classic CSRF doesn't apply.
- All text is inserted with `textContent`, so messages can't inject HTML.
- The token lives in `localStorage`. That is fine for a prototype; a stricter setup would use HttpOnly cookies.
- JSON is a prototype database. For many users, switch to SQLite or PostgreSQL.

## Version 2

New: reactions and emoji, replies, editing and deleting messages, file / picture / video uploads, chat backgrounds,
clearing chats, reports and moderators, an extended admin area (create users, roles, delete users completely,
settings, audit log) and a loading screen with picture and music.

### What changed in the data
- Messages now live in real tables (`messages`, `reactions`, `attachments`, `reports`, `audit_log`, ...).
  Neon/PostgreSQL if `DATABASE_URL` is set, otherwise a local SQLite file `backend/data/chatisfying.db`.
- On the first start the old messages are copied into the new table automatically. Make a backup of your Neon database first.
- Users, groups, invitations and settings stay in the key-value store (`storage.py`), as before.

### Roles
`user` < `moderator` < `admin`. The account named in `ADMIN_USERNAME` is the protected main admin.
Moderators can delete messages, mute people (timeouts) and handle reports. Admins can do everything.

### Privacy rules for admins
1. Group chats: admins may read them (the group info says so).
2. Private chats: not readable by default. Admins see reported messages (with context) and can clear a chat without reading it.
3. Emergency access: needs a written reason. Both people see a notice in the chat and the audit log records it.

### File storage (needed for uploads and the loading screen)
Files go from the browser straight into an S3-compatible bucket (for example Backblaze B2 or Cloudflare R2).
The server only creates short-lived signed links. Set these variables on the server (never in GitHub):

```
S3_ENDPOINT_URL=...   S3_REGION=...   S3_BUCKET=...   S3_ACCESS_KEY_ID=...   S3_SECRET_ACCESS_KEY=...
```

Steps (check the provider's current documentation for the exact menu names):
1. Create a **private** bucket and an access key that may read and write only this bucket.
2. Note the S3 endpoint and region the provider shows for the bucket.
3. Add a CORS rule to the bucket: allowed origin = your frontend address (for example `https://YOURNAME.github.io`),
   methods `PUT`, `GET`, `HEAD`, allowed header `Content-Type`. Without it the browser blocks uploads.
4. Without these variables everything else still works; uploads and the loading screen are switched off.

Limits (maximum sizes, quota per person, blocked file types) are set in **Admin -> Settings**. The hard cap is 200 MB per file.

### Still open
Typing indicators, unread counters, push notifications, password reset by email, two-factor login for admins.
Remove the debug output (verification codes in the log, `/debug`, request logs) before real use.


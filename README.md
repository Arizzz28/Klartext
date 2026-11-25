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

### Roles (replaced by ranks in Version 3)
Version 2 had the fixed roles `user` < `moderator` < `admin`. Version 3 replaces them with ranks and permissions (see below).

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

### Still open after Version 2
Typing indicators, password reset by email, two-factor login for admins.


---

## Version 3

### The idea: ranks and permissions
- A **rank** is a named bundle of permissions: Basic, Pro, Pro+, Pro++, Pro+++, Mod, Admin, Owner.
- Every single feature is **its own permission** (for example `tabs.calendar`, `chat.inspect`, `games.memory`, `tabs.bubble`, `tabs.editor`).
  The server checks it on **every request** (`security.perm_required` / `security.need`). The frontend only hides buttons.
- The **Owner** (the username in `OWNER_USERNAME`) always has every permission and the top rank. The Owner creates, renames,
  edits and deletes ranks under **Admin -> Ranks**, decides which rank gets which design, and decides which statistics admins see.
- Nobody can change someone whose rank is **not below** their own. Nobody can touch the Owner.
- Admins can send **permission requests** to the Owner (Admin -> "Ask the Owner"); the Owner approves or denies, and approved
  permissions are added to that person on top of their rank.
- **Pro offers:** people offer something instead of paying (help, an idea, a favour). Admins are notified, read it and may
  reward the person with a temporary rank. The Owner writes the rules text. **No real money is involved.**
- **Coins and missions:** missions (for example "write 10 messages today") give coins. With coins people can **rent a rank**
  for a few days (the Owner sets the shop and the longest rental). Admins and the Owner can gift coins and temporary ranks within
  limits the Owner sets. A rented or gifted rank never lowers someone's own rank.

### What is new
Design modes (Classic, Glass, Paper, Midnight, Neon; the rank decides which ones you may use), a roomier layout with a bigger
message area, a movable translucent **tab bubble** and a **tab editor**, movable sidebars (left/right, chat list inner/outer, width by dragging),
unread counters on chats and tabs that work across devices, notifications, **push messages when someone writes**, and the tabs:
missions and coins, calendar, tasks, widgets, global search, music links, profile visitors, custom tabs, notes, games
(Tic-Tac-Toe, number guess, memory), forum / suggestions, AI (Gemini), What's New (with per-person "seen"), optional ads.
Admin area: users with ranks, whitelist, groups, private-chat overview (who talks to whom, no text), reports, Pro offers,
permission requests, notes access, What's New, ads, ranks editor, settings, audit log.

### What is NOT built (please read)
- **Group voice channels are not built.** The permission `tabs.voice` exists so ranks can be prepared, and the ranks editor marks it "not built yet".
- There are no real payments. Coins have no money value.
- Music is **links only** (YouTube, SoundCloud, Spotify, Bandcamp, Apple Music, Deezer, Tidal, Audiomack). Nothing is hosted or played by the server.

### Migration from Version 2 (nothing is lost)
On the first start the server creates the new tables itself (`CREATE TABLE IF NOT EXISTS`), creates the standard ranks, and gives **every
existing account the Basic rank**. The account named in `OWNER_USERNAME` becomes Owner. Users, groups, messages and files stay as they are.
Everybody has to accept the new terms once at the next login (the server enforces this). Make a backup of your Neon database first
(Neon console -> your branch -> "Backups" / or export with `pg_dump`).
Old rank data in `users` (`role`) is ignored from now on.

### New settings (environment variables, on Render)
| Variable | Meaning |
|---|---|
| `OWNER_USERNAME` | The Owner account (for example `Aris`). Falls back to `ADMIN_USERNAME`. |
| `DEBUG_LOG_CODES` | `1` prints verification codes into the log. **Default off.** Turn on only to debug email. |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | Push messages. Create the keys once with `python gen_vapid.py`. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | AI tab. Off until the Owner switches it on in Settings. |

### Push messages on an iPad
Push works on iPadOS/iOS (16.4 or newer) **only** for a web app on the Home Screen: open the site in Safari, tap Share -> "Add to Home Screen",
open Chatisfying from that icon, then turn push on in **Settings -> Push notifications**. Push messages carry only the sender's name unless the
receiver switches on "Show the message text". They pass through the push service of the browser / device maker.

### AI tab: what you must know before switching it on
**It is off by default, and for an operator in Germany it probably has to stay off unless you use a paid Google account.**
The key lives only on the server. According to Google's Gemini API Additional Terms (effective March 23, 2026, read on 2026-11-25; please re-read them, they change):
- For the **unpaid** tier, Google may use the content to improve its products and **human reviewers may read it**; do not submit sensitive, confidential or personal information.
- In the **EEA, Switzerland and the UK** you "may use only Paid Services when making API Clients available to users". A messenger that you offer to other people is such an API client. "Paid" means a Google Cloud project with an active billing account, which needs a payment method. That conflicts with the "0 EUR, no credit card" goal.
- You must be 18+, and the API client must not be directed at or likely to be used by people under 18.
So: leave the AI tab **off** unless you are sure these terms allow your use. The app still shows a notice, needs a one-time confirmation per person, sends **nothing** from chats unless the
person ticks it for that question, asks for an extra confirmation for private chats (the other person's messages would go to Google), and has a daily limit per person.

### Legal pages (terms, privacy, imprint)
- `frontend/terms.html`, `privacy.html`, `imprint.html` are written from what the code really does. They are **not legal advice** and each lists
  its **open points** at the bottom. Operator details (name, address, email, minimum age) come from **Admin -> Settings -> Owner: legal details**;
  until you fill them in, the pages show clearly marked gaps. Nothing is invented.
- Registration has exactly one checkbox, not preselected: "Ich akzeptiere die Nutzungsbedingungen". The server checks it, and stores the
  version and the time (`user.consent`). When you change the texts in a way that matters, raise `TERMS_VERSION` / `PRIVACY_VERSION`
  in `backend/legalconf.py`: everybody then has to accept again.
- Existing accounts see a consent dialog at their next login.

### Tests
```bash
cd backend
pip install pytest
python -m pytest -q tests          # SQLite;  with TEST_DATABASE_URL=postgresql://... it runs on PostgreSQL
```
The tests cover ranks and the hierarchy, every permission being enforced on the server, consent, notes access logging, offers,
coins/missions/shop, unread counters, push, the AI rules (key never leaves the server, private chats need consent), account deletion
(including the data of the new tabs) and that every API route needs a login (except the explicitly public ones).

### Where is what (Version 3 additions)
| File | Job |
|---|---|
| `backend/perms.py` | All permission keys, ranks, the rank/lease/extra-permission logic, designs |
| `backend/legalconf.py` | Versions of the legal texts and the consent check |
| `backend/notify.py` | Notifications, unread counters, push |
| `backend/economy.py` | Missions, coins, shop, gifts |
| `backend/offers.py`, `notes.py`, `planner.py`, `social.py`, `extras.py`, `games.py`, `ai.py` | The new tabs |
| `backend/admin.py` | Admin routes, split by permission |
| `frontend/tabs.js` | Which tabs exist and which permission each needs |
| `frontend/pages/admin.js`, `admin_owner.js` | Admin area (tabs appear by permission) |
| `frontend/consent.js`, `legal.js`, `terms.html`, `privacy.html`, `imprint.html` | Legal texts and consent |
| `frontend/push.js`, `sw.js`, `manifest.webmanifest` | Push and "Add to Home Screen" |

### Known limits / open points
- The in-memory rate limit and the single-process lock mean: run **one** server process.
- `/debug` still exists from Version 2. Remove it before you invite many people.
- There is no "delete my own account" button and no data export yet; the operator does that on request (the privacy text says so).
- Login log, audit log and reports have **no automatic deletion** yet.
- Whether and how a legal operator duty applies to you (imprint, GDPR controller role, minimum age) is **a legal question**. Please ask someone qualified.

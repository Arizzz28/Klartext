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
- `/debug` still exists, but it now only shows that the server runs and which build it is (no settings, no route list).
- People can download their data and delete their own account (Settings -> "Your data"). Deleting an account deletes its
  **private chats for both sides**; this is said in the dialog and in the texts.
- Login log, audit log and reports have **no automatic deletion** yet.
- Whether and how a legal operator duty applies to you (imprint, GDPR controller role, minimum age) is **a legal question**. Please ask someone qualified.


## Version 3.1: review, security, new pages, start page

### What the review found and changed
| | Finding | Change |
|---|---|---|
| important | `/debug` listed settings and routes to everybody | now only `status` and `build` |
| important | Push subscriptions accepted **any** https address; the server then called it (SSRF) | only the push services of Apple, Google, Mozilla and Microsoft are accepted (`notify.py`) |
| important | No security headers on the API | `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store`, a strict `Content-Security-Policy` on every answer |
| important | Deleting an account left moderation reports (copies of messages) behind | reports filed by the person or containing their messages are deleted, too |
| important | No way to delete your own account or to get your data | Settings -> "Your data" (`backend/accounts.py`); works even without accepting new Terms |
| useful | A blocked account saw an error page with no way out | the error page now has a "Log out" button |
| useful | Page list was repeated in `users.py` | now only `frontend/tabs.js` (see below) |
| new | Start page after login | configurable (see below) |

Tested and found **safe**: a normal user cannot read or change other people's chats, groups, files, notes, calendar, tasks, playlists,
forum posts, notifications; cannot reach any admin route; cannot raise their own rank (mass assignment); cannot get at the Owner.
The tests are in `backend/tests/test_security.py` (run `cd backend && python -m pytest tests -q`). They also walk over **every** API
route and check that it refuses requests without a login, and they check that the frontend never builds HTML from data.

### Add a new page (3 steps, no regeneration of the project)
1. **Copy** `frontend/pages/_new_page_template.js` to `frontend/pages/<name>.js` and write your page (it fills the empty `main` element).
2. **Register it** with one line in `frontend/tabs.js`:
   `import * as recipes from "./pages/recipes.js";` and `{ id: "recipes", label: "Recipes", icon: "page", page: recipes, perm: "tabs.recipes" }`
   in the `TABS` list. The navigation, the tab bubble, the tab editor, the start-page choice and the default sidebar pick it up automatically.
   Leave out `perm` for a page everybody may see; add `pinned: false` if it should not be in the sidebar until a person adds it.
3. **If the page has its own data**, add the server side: a blueprint in a new `backend/<name>.py` with routes protected by
   `@perm_required("tabs.recipes")`, register it in the list in `backend/app.py`, and add the permission key `("tabs.recipes", "Recipes", "Features")`
   to the list in `backend/perms.py`. Then give the permission to the ranks that should have it (Admin -> Ranks; the Owner always has it).
   **Hiding a tab is only convenience. The server must check the permission on every route.**
If a rank does not have the permission, the tab is simply not shown and its address sends the person to Chats (never in a loop).

### Start page after login
- The Owner sets the default for everybody: **Admin -> Settings -> General -> Start page after login**.
- Everybody can choose their own: **Settings -> Start page** ("Default" = the Owner's choice).
- Order: own choice -> Owner's default -> Chats. A page the person is not allowed to see is skipped. Links with a page in them
  (for example from a notification) always open that page. The Back button does not return to the empty address.

### Rate limit behind a proxy (optional, `PROXY_HOPS`)
Render puts its own proxy in front of the server. Without a setting, the server sees the **proxy's** address for every visitor.
That is why the lock after wrong passwords is also tied to the **username** (not only the address). It works, but one person who
guesses wrong passwords for a username can lock that username for a while.
`PROXY_HOPS=0` (default) is always safe. Set `PROXY_HOPS=1` **only** after you checked that exactly one proxy stands in front of
the server (Render's documentation / a test with a request showing `X-Forwarded-For`). A wrong number lets visitors fake their address.

## Version 4: games, missions, plans, windows, PC server

### What is new
- **Missions**: action "none" = free (the person just presses collect). Random mode: each person gets slots per hour/day/week; every mission has a rarity (common, uncommon, rare, super rare, impossible) with a chance set by the Owner. Translation missions: a person translates texts into German, an admin checks, then the points come.
- **Plans tab**: ranks, benefits, offers. The ranks Pro+, Pro++, Pro+++ are hidden by default (Owner can show them again: Ranks → "offered"). The text about supporting the servers is set by the Owner (Settings → Owner: Plans tab). **No payment is built.** See "Open points" below.
- **Games**: Tic-Tac-Toe, Word race, Checkers, Chess, Memory, Typing duel (against a person, the computer or alone), Reaction, Aim trainer, Number guess, 3D maze, Shooter. Games unlock one after the other by points; the order, the points and on/off are set by admins (Admin → Settings → Games). Which rank gets which game is the normal permission list (Owner → Ranks, "Game: …").
- **Computer levels**: easy (random moves), medium (sometimes smart), hard (mostly smart, a little random), impossible (Tic-Tac-Toe: can not be beaten; chess: looks 3 moves ahead; other games: the strongest setting).
- **Elo**: only for games between two people. Start 1000, K = 32. Beating a stronger person gives more points.
- **Fun tab** (3 own ideas): daily streak with coins, badges (calculated from what you did), polls.
- **Prank tab**: pranks only reach people who switched them on themselves. The jumpscare is an original drawing, not a character from a game.
- **Window mode** (permission "layout.windows"): bubble → "Window mode: on". Tabs open as movable windows, can be folded into the dock and several can be open (Owner sets the maximum).
- **PC server** (see below) and **speed** improvements (fewer requests, no repeated identical requests, light polling).
- **Video calls**: not built. Plan: 1:1 calls with WebRTC (the browsers talk directly), our server only passes the "who calls whom" notes. It needs a STUN server (a free one from Google is common; that is a third party and must go into the privacy text) and for strict networks a TURN server (costs money). Group calls need much more. Ask before this is started.

### Fixing the Backblaze upload ("The upload failed. Check your connection.")
This message is almost always a CORS problem: the browser is not allowed to send the file to Backblaze directly.
1. In Admin → Settings (Owner) use the storage check (`/api/admin/storage-check`): it tells you what is wrong.
2. Set the CORS rule with the script (once, on any computer, with a **temporary** Backblaze key that has the right to change bucket settings; delete that key afterwards):
   `python setup_cors.py --origin https://arizzz28.github.io --bucket klartext-storage --endpoint https://s3.eu-central-003.backblazeb2.com --key-id KEY_ID --key APPLICATION_KEY`
   The origin has **no** slash at the end and no path (`/Klartext` does not belong in it).
3. Never change the bucket to public. The files stay private; the server hands out short-lived links.

### PC server (your PC does the computing)
What it is: the same backend runs on your Windows PC. Data stays in Neon and Backblaze, so the PC needs no files and nothing is lost when it is off. If the PC is off, a message appears and the normal server (Render) is used. If you get money for servers later, you can upgrade Render and you may not need the PC at all.
Set-up:
1. On Render add the variable `PC_SECRET` (a long random text, e.g. `python -c "import secrets; print(secrets.token_hex(24))"`).
2. On the PC: put the `backend` folder somewhere, copy `.env.pc.example` to `.env.pc` and fill it in (same values as on Render + the same `PC_SECRET`). Put `cloudflared.exe` (free from Cloudflare) next to `pc_agent.py`, or write your own tunnel address into `PC_PUBLIC_URL`.
3. Double-click `start_pc_backend.bat`. Keep the window open. After about a minute Admin → Settings shows "PC is online".
4. Admin (Owner) → Settings → "Use my PC as an extra server" on. Ranks → permission "Use the PC server" for the ranks you want (default: Pro+++). Each person also switches it on in Settings.
Safety: `.env.pc` holds the keys to your database – never share it. The PC accepts the same login tokens as Render. Only the heartbeat route is open without login and it needs the secret. The tunnel (Cloudflare) is a third party that sees the traffic; it is in the privacy text. Do not run the PC server on a school or work computer.

### Changing games yourself (without asking anybody)
- **Add or remove a game from the list**: `backend/games.py`, list `GAMES` (id, name, text, kind). Also give it a permission default in `backend/perms.py` (`NEW_DEFAULTS`).
- **Change the unlock points / order**: no code needed, Admin → Settings → Games. Defaults live in `DEFAULT_UNLOCK` and `DEFAULT_ORDER` in `games.py`.
- **Points for wins**: `WIN_POINTS`, `HUMAN_WIN`, `HUMAN_DRAW`, `PLAY_POINTS` in `games.py`.
- **How strong the computer is**: `TTT_STRENGTH` (Tic-Tac-Toe, chance of a perfect move), `BOT_GUESS_CHANCE` in `matches.py` (Word race), depth in `ch_bot` (chess) – all in `backend/gamelogic.py`.
- **Rules of a board game**: `backend/gamelogic.py`. Every game has `new`, `move`, `view`, `bot` functions and is listed in `GAMES` at the bottom. The server runs the rules, the browser only draws (`frontend/pages/games.js`, object `BOARDS`).
- **A new single-player game**: write a function in `frontend/pages/games_solo.js`, add it to `SOLO`, add an entry with `"kind": "solo"` and `limits` in `games.py` (the limits stop impossible scores).
- After every change run the tests: `cd backend && python -m pytest tests -q`.

### Open points (for you and your parents)
1. **Taking money.** The app has no payment on purpose. If classmates give you money for ranks or servers, that is a different legal situation: imprint/provider details (§ 5 DDG), taxes, and as a minor you need your parents (they are legally responsible). The texts mention this but are not legal advice. Ask your parents before you collect anything.
2. **Legal texts** were updated (games, pranks, PC server, polls, translations). Parents should read them again; versions changed, so everybody has to accept them once more.
3. **"Levels"** in your list was understood as "hide the ranks Pro+/Pro++/Pro+++". Tell me if you meant something else.
4. **Pranks**: please test the jumpscare on yourself first. Loud sudden things can scare people; that is why it is opt-in.
5. **Video calls** and a real 3D engine are only planned (see above).
6. The **Backblaze CORS problem** needs the script above to be run once (I can not reach your Backblaze account).

# Blind Date Bot

An anonymous matchmaking Telegram bot built with **aiogram 3**, **MongoDB Atlas**
(via **Motor**), and deployed as a background worker on **Render**.

## Features

- Guided profile creation (name, age, gender, preference, city, bio, photo)
- Profile editing via inline menu
- Anonymous 1-to-1 matchmaking based on mutual gender preference
- Live message relay between matched partners (text, photos, voice, video, etc.)
- "Next partner", "Stop chat", and "Report" controls
- Race-condition-safe matching using atomic MongoDB updates
- Admin commands: `/ban`, `/unban`, `/stats`

## Tech Stack

| Component | Choice |
|---|---|
| Language | Python 3.12 |
| Bot framework | aiogram 3 |
| Database | MongoDB Atlas |
| Driver | Motor (async) |
| Hosting | Render (background worker) |

## Project Structure

```
blind-date-bot/
├── app.py                     # Entry point
├── config.py                  # Env-based configuration
├── database/
│   ├── db.py                  # Motor connection + indexes
│   └── models.py              # Pydantic models
├── handlers/
│   ├── start.py                # /start, /help
│   ├── admin.py                 # /ban, /unban, /stats
│   ├── profile.py               # Registration + profile editing
│   ├── search.py                 # Matchmaking entry point
│   └── chat.py                    # In-chat relay, next/stop/report
├── keyboards/
│   ├── main_kb.py
│   └── profile_kb.py
├── matching/
│   └── match_service.py         # Core matchmaking logic
├── utils/
│   └── states.py                 # FSM state groups
├── requirements.txt
├── runtime.txt
├── render.yaml
├── .gitignore
└── .env.example
```

## Local Setup

1. Clone the repo and create a virtual environment:
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```

4. Run the bot:
   ```bash
   python app.py
   ```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | Token from [@BotFather](https://t.me/BotFather) |
| `MONGO_URI` | ✅ | MongoDB Atlas connection string |
| `MONGO_DB_NAME` | ❌ | Database name (default: `blind_date_bot`) |
| `ADMIN_IDS` | ❌ | Comma-separated Telegram user IDs with admin access |
| `MIN_AGE` / `MAX_AGE` | ❌ | Age bounds for registration (default 18–99) |
| `ENVIRONMENT` | ❌ | `development` or `production` |

## Admin Commands

Only usable by Telegram user IDs listed in `ADMIN_IDS`:

- `/ban <telegram_id>` — bans a user, ends any active chat they're in
- `/unban <telegram_id>` — restores a banned user to active status
- `/stats` — shows total users, active/searching/in-chat counts, and report count

## Deploying to Render

1. Push this repo to GitHub — **make sure the folder structure is preserved**
   (`database/`, `handlers/`, `keyboards/`, `matching/`, `utils/` must all be
   actual subfolders, not flattened files).
2. In Render, choose **New → Blueprint** and point it at your repo (uses `render.yaml`).
3. Set the secret env vars (`BOT_TOKEN`, `MONGO_URI`, `ADMIN_IDS`) in the Render
   dashboard — they're marked `sync: false` so Render will prompt for them.
4. Deploy. Render will run `pip install -r requirements.txt` then `python app.py`
   as a long-running **worker** (polling mode — not a web service, no port needed).

## MongoDB Atlas Setup

1. Create a free-tier cluster on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
2. **Database Access** → create a database user with a strong password.
3. **Network Access** → add `0.0.0.0/0` (Allow Access from Anywhere) — Render does
   not use static IPs, so this is required. Make sure the entry is **not** set to
   expire/temporary.
4. Copy the connection string into `MONGO_URI`, replacing `<username>`/`<password>`.
   URL-encode any special characters in the password.
5. Indexes are created automatically on startup via `ensure_indexes()`.

## Notes

- The bot uses **long polling**, not webhooks — deploy it as a Render
  **Background Worker**, not a Web Service (a Web Service will warn about "no
  open ports" since the bot never binds to one).
- Matching is race-condition-safe via atomic `find_one_and_update` claims in
  `matching/match_service.py`.
- Reports are stored in the `reports` collection; banned users are blocked from
  registration, search, and chat relay.
- TLS connections to Atlas use `certifi`'s CA bundle explicitly (`database/db.py`)
  to avoid handshake failures on some container platforms.

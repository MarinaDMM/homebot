# Mari's Telegram bot

A personal assistant that lives on your Mac. It sends reminders, reads your inbox for events to add to Calendar, briefs you in the morning, and controls HomeKit (lights + locks) — all over Telegram.

## What it does

- **Reminders** via chat. `/remind every Tuesday 19:00 take out trash`. Recurring or one-off.
- **Morning briefing** at 08:00: weather, KNMI alerts, today's calendar, trash if pickup is today/tomorrow.
- **Email → Calendar.** Polls Gmail every 30 min. When Claude spots an event (flight, doctor, restaurant), the bot DMs you with `Add` / `Skip` buttons.
- **HomeKit control** through Apple Shortcuts. `/lights on`, `/scene movie`, `/lock front` (with confirm step).
- **Trash schedule** for Dutch postcodes via mijnafvalwijzer.nl.

## Architecture (one-liner)

`Telegram ↔ python-telegram-bot ↔ APScheduler ↔ {SQLite, Gmail API, Calendar API, Buienradar, mijnafvalwijzer, KNMI, /usr/bin/shortcuts}`

## Setup — one-time

### 1. Install Python deps

```sh
cd ~/mari-bot                     # or wherever you put this folder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Get your Telegram details

You said you have a bot token already — copy it.

For your user ID: open Telegram, message `@userinfobot`, copy the number.

Edit `config.yaml`:
```yaml
telegram:
  bot_token: "1234567890:ABC..."
  authorized_user_id: 123456789
```

### 3. Set up Google OAuth (Gmail + Calendar)

This takes ~5 minutes.

1. Go to https://console.cloud.google.com/projectcreate. Name it "mari-bot" (or anything). Create.
2. In the new project, enable the APIs:
   - https://console.cloud.google.com/apis/library/gmail.googleapis.com → **Enable**
   - https://console.cloud.google.com/apis/library/calendar-json.googleapis.com → **Enable**
3. Configure the OAuth consent screen: https://console.cloud.google.com/apis/credentials/consent
   - User type: **External**
   - App name: `mari-bot`
   - Support email + developer email: your address
   - **Add yourself as a test user** under "Test users" (this lets you skip Google's verification)
   - Save
4. Create the OAuth client: https://console.cloud.google.com/apis/credentials → **+ Create credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name: `mari-bot-desktop`
   - Create → click **Download JSON**
5. Save the downloaded file as `google_credentials.json` in this folder.

First time you run the bot, a browser window will pop up asking you to log in — pick your Google account, click through the unverified-app warning ("Advanced → Go to mari-bot (unsafe)" — that's expected for a personal app), and grant access. After that it caches `google_token.json` and is silent forever.

### 4. Set your location

In `config.yaml` under `location:`, fill in your postcode (no spaces, e.g. `1011AB`), house number, and lat/lon. Find lat/lon at https://www.latlong.net.

### 5. Anthropic API key (for email scanning)

The email-to-calendar feature uses Claude. Get an API key at https://console.anthropic.com/, paste under `llm.anthropic_api_key`. Leave blank to disable email scanning (everything else works without it).

### 6. Create the HomeKit shortcuts

See `shortcuts-to-create.md`. Six shortcuts in the Shortcuts app, ~10 minutes.

After creating them, grant permissions on the first run (macOS will prompt).

### 7. Test run

```sh
source .venv/bin/activate
python bot.py
```

Open Telegram, send `/start` to your bot. You should get a help message back.

Try:
- `/weather`
- `/trash`
- `/remind in 1 minute test reminder`
- `/lights on`

If everything works, stop with Ctrl-C and move on to step 8.

### 8. Auto-start on login (LaunchAgent)

Edit `launchagent/com.mari.bot.plist` — replace `YOUR_USERNAME` (3 places) with your Mac username (`whoami`).

Install it:

```sh
cp launchagent/com.mari.bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mari.bot.plist
launchctl start com.mari.bot
```

To check it's running:
```sh
launchctl list | grep mari
tail -f launchd.out.log
```

To restart after editing config:
```sh
launchctl kickstart -k gui/$(id -u)/com.mari.bot
```

To uninstall:
```sh
launchctl unload ~/Library/LaunchAgents/com.mari.bot.plist
```

## Commands

| Command | Example |
|---|---|
| `/remind <when> <text>` | `/remind every Tuesday 19:00 take out trash` |
| `/list` | Show active reminders |
| `/delete <id>` | Remove reminder #3 |
| `/lights on\|off` | Toggle lights |
| `/scene <name>` | Run a HomeKit scene |
| `/lock <name>` / `/unlock <name>` | Lock or unlock (asks for confirmation) |
| `/shortcuts` | List all Shortcuts available to the bot |
| `/weather` | Now + today's forecast + KNMI alerts |
| `/trash` | Upcoming pickups |
| `/today` | Today's calendar |
| `/briefing` | Full briefing now (same content as the 08:00 push) |

### Reminder formats accepted

- `every Tuesday at 19:00 take out trash`
- `every weekday 9am standup`
- `every Mon, Wed, Fri 7am gym`
- `tomorrow 14:30 dentist`
- `today 22:00 take vitamins`
- `in 2 hours water plants`
- `on 2026-05-15 16:00 pick up package`

## Troubleshooting

**Shortcuts permission denied**: open System Settings → Privacy & Security → Automation, find Terminal (or your shell), allow Shortcuts.

**Gmail OAuth keeps re-prompting**: delete `google_token.json` and re-run.

**Bot silent after a while**: check `bot.log` and `launchd.err.log`. Usually Telegram rate-limited briefly; APScheduler keeps queueing.

**KNMI/Buienradar timeouts**: they're flaky occasionally. The bot logs and continues.

## Suggestions you might want next

- **Quiet hours** — pause reminders 23:00–07:00.
- **Snooze buttons** on reminders ("snooze 1h" / "snooze tomorrow").
- **Geofence-aware reminders** — only fire when you're home (requires a phone shortcut that pings the bot via webhook).
- **NS train delays** — alert if your usual route is disrupted.
- **Speech**: send a voice memo to the bot, transcribe with Whisper, parse as command.
- **Shared with a partner**: change `authorized_user_id` to a list and add per-user permission rules.
